"""
vetgpt/backend/schedule_routes.py

Scheduling API — create, list, complete events. Register push tokens.

Routes:
  POST /api/schedules/generate        — LLM generates schedule from natural language
  POST /api/schedules/from-template   — create schedule from a named template
  GET  /api/schedules                 — list all my upcoming events
  GET  /api/schedules/today           — events due today
  GET  /api/schedules/{id}            — get single event
  PUT  /api/schedules/{id}            — update event (reschedule, change reminder)
  POST /api/schedules/{id}/complete   — mark event done
  DELETE /api/schedules/{id}          — delete event

  POST /api/schedules/push-token      — register Expo push token
  DELETE /api/schedules/push-token    — unregister push token

  GET  /api/schedules/templates       — list available templates
"""

import uuid
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .database import get_db, User
from .schedule_models import ScheduledEvent, PushToken, EventStatus, NotificationChannel
from .schedule_templates import SCHEDULE_TEMPLATES, get_template
from .config import get_settings

settings    = get_settings()
sched_router = APIRouter(prefix="/api/schedules", tags=["schedules & reminders"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class GenerateScheduleRequest(BaseModel):
    text:            str                    # "I bought 200 chicks today"
    farm_id:         Optional[str] = None
    animal_id:       Optional[str] = None
    language:        str           = "en"
    reminder_days:   list[int]     = [3, 1, 0]   # days before event to notify
    notify_channels: list[str]     = ["push"]    # push, telegram, whatsapp

class FromTemplateRequest(BaseModel):
    template_key:    str                    # "chick_vaccination"
    start_date:      str                    # ISO date: "2025-06-01"
    schedule_name:   str                    # "Batch A — June chicks"
    farm_id:         Optional[str] = None
    animal_id:       Optional[str] = None
    reminder_days:   list[int]     = [3, 1, 0]
    notify_channels: list[str]     = ["push"]

class UpdateEventRequest(BaseModel):
    event_date:      Optional[str]      = None
    reminder_days:   Optional[list[int]]= None
    notify_channels: Optional[list[str]]= None
    title:           Optional[str]      = None
    description:     Optional[str]      = None

class CompleteEventRequest(BaseModel):
    notes: str = ""

class PushTokenRequest(BaseModel):
    token:       str
    device_name: str = ""
    platform:    str = ""    # ios | android


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _event_to_dict(e: ScheduledEvent) -> dict:
    return {
        "id":               e.id,
        "schedule_name":    e.schedule_name,
        "template_key":     e.template_key,
        "species":          e.species,
        "farm_id":          e.farm_id,
        "animal_id":        e.animal_id,
        "title":            e.title,
        "description":      e.description,
        "event_date":       e.event_date.isoformat() if e.event_date else None,
        "is_critical":      e.is_critical,
        "reminder_days":    [int(d) for d in e.reminder_days.split(",") if d.strip()],
        "notify_channels":  e.notify_channels.split(","),
        "status":           e.status.value,
        "completed":        e.completed,
        "completed_at":     e.completed_at.isoformat() if e.completed_at else None,
        "completion_notes": e.completion_notes,
        "days_until":       (e.event_date - datetime.utcnow()).days if e.event_date else None,
    }


async def _create_events_from_list(
    events_data: list[dict],
    user_id: str,
    farm_id: Optional[str],
    animal_id: Optional[str],
    schedule_name: str,
    template_key: str,
    species: str,
    reminder_days: list[int],
    notify_channels: list[str],
    db: AsyncSession,
) -> list[ScheduledEvent]:
    created = []
    for ev in events_data:
        event = ScheduledEvent(
            id              = str(uuid.uuid4()),
            user_id         = user_id,
            farm_id         = farm_id,
            animal_id       = animal_id,
            schedule_name   = schedule_name,
            template_key    = template_key,
            species         = species,
            title           = ev["title"],
            description     = ev.get("description", ""),
            event_date      = ev["event_date"],
            is_critical     = ev.get("is_critical", False),
            reminder_days   = ",".join(str(d) for d in reminder_days),
            notify_channels = ",".join(notify_channels),
        )
        db.add(event)
        created.append(event)
    await db.flush()
    return created


# ─── LLM schedule generation ──────────────────────────────────────────────────

async def _generate_schedule_with_llm(
    text: str,
    language: str,
    user_id: str,
) -> dict:
    """
    Use the RAG LLM to parse natural language and generate a schedule.

    Returns:
      {
        "schedule_name": str,
        "template_key":  str,
        "species":       str,
        "start_date":    "YYYY-MM-DD",
        "events": [
          {
            "title": str,
            "description": str,
            "day_offset": int,
            "is_critical": bool
          }
        ]
      }
    """
    today     = datetime.utcnow().strftime("%Y-%m-%d")
    templates = "\n".join(
        f"- {k}: {t.name} ({t.species})"
        for k, t in SCHEDULE_TEMPLATES.items()
    )

    prompt = f"""Today's date is {today}.
The user said: "{text}"

Available schedule templates:
{templates}

Task:
1. Identify what schedule the user wants to create.
2. Determine the start date (default to today if not specified).
3. Select the most appropriate template key, or create a custom schedule.
4. Generate the full list of events with their dates.

Respond ONLY with a valid JSON object in this exact format:
{{
  "schedule_name": "descriptive name e.g. Batch A Chick Vaccination",
  "template_key": "chick_vaccination",
  "species": "poultry",
  "start_date": "YYYY-MM-DD",
  "events": [
    {{
      "title": "Day 7 — Newcastle Disease Vaccine",
      "description": "Administer via drinking water...",
      "day_offset": 7,
      "is_critical": true
    }}
  ]
}}

Use the template events if a matching template exists.
Adjust dates relative to the start_date.
Respond in {language} for title and description fields.
Return ONLY the JSON object, no other text."""

    # Call LLM (Ollama or cloud)
    import httpx
    if settings.llm_provider == "ollama":
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model":  settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 2000},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
    elif settings.anthropic_api_key:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg    = await client.messages.create(
            model      = settings.llm_model_anthropic,
            max_tokens = 2000,
            messages   = [{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text
    elif settings.openai_api_key:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp   = await client.chat.completions.create(
            model    = settings.llm_model_openai,
            messages = [{"role": "user", "content": prompt}],
            max_tokens = 2000,
            temperature = 0.1,
        )
        raw = resp.choices[0].message.content
    else:
        raise HTTPException(503, "No LLM configured.")

    # Parse JSON from response
    import re
    match = re.search(r'\{[\s\S]+\}', raw)
    if not match:
        raise HTTPException(500, "LLM did not return valid JSON schedule.")
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"LLM returned invalid JSON: {e}")


# ─── Routes ───────────────────────────────────────────────────────────────────

@sched_router.get("/templates")
async def list_templates(_: User = Depends(get_current_user)):
    """List all available schedule templates."""
    return [
        {
            "key":         k,
            "name":        t.name,
            "species":     t.species,
            "description": t.description,
            "event_count": len(t.events),
        }
        for k, t in SCHEDULE_TEMPLATES.items()
    ]


@sched_router.post("/generate", status_code=201)
async def generate_schedule(
    body: GenerateScheduleRequest,
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """
    Generate a veterinary schedule from natural language.

    Examples:
      "I bought 200 chicks today"
      "My cow Daisy was served on 15th June"
      "Start deworming programme for my cattle herd next Monday"
      "Nilinanua vifaranga 100 leo" (Swahili)
    """
    result = await _generate_schedule_with_llm(body.text, body.language, user.id)

    start_date = datetime.strptime(result["start_date"], "%Y-%m-%d")
    events_data = [
        {
            "title":       ev["title"],
            "description": ev.get("description", ""),
            "event_date":  start_date + timedelta(days=ev["day_offset"]),
            "is_critical": ev.get("is_critical", False),
        }
        for ev in result.get("events", [])
    ]

    if not events_data:
        raise HTTPException(422, "LLM generated no events. Try being more specific.")

    created = await _create_events_from_list(
        events_data    = events_data,
        user_id        = user.id,
        farm_id        = body.farm_id,
        animal_id      = body.animal_id,
        schedule_name  = result["schedule_name"],
        template_key   = result.get("template_key", "custom"),
        species        = result.get("species", ""),
        reminder_days  = body.reminder_days,
        notify_channels= body.notify_channels,
        db             = db,
    )

    return {
        "schedule_name": result["schedule_name"],
        "template_key":  result.get("template_key", "custom"),
        "species":       result.get("species", ""),
        "events_created": len(created),
        "events":        [_event_to_dict(e) for e in created],
        "message":       f"Created {len(created)} scheduled reminders.",
    }


@sched_router.post("/from-template", status_code=201)
async def schedule_from_template(
    body: FromTemplateRequest,
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Create a schedule directly from a named template."""
    template = get_template(body.template_key)
    if not template:
        raise HTTPException(404, f"Template '{body.template_key}' not found. GET /api/schedules/templates for list.")

    try:
        start_date = datetime.strptime(body.start_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, "start_date must be YYYY-MM-DD format.")

    events_data = [
        {
            "title":       ev.title,
            "description": ev.description,
            "event_date":  start_date + timedelta(days=ev.day_offset),
            "is_critical": ev.critical,
            "reminder_days": ev.reminder_days or body.reminder_days,
        }
        for ev in template.events
    ]

    created = await _create_events_from_list(
        events_data    = events_data,
        user_id        = user.id,
        farm_id        = body.farm_id,
        animal_id      = body.animal_id,
        schedule_name  = body.schedule_name,
        template_key   = body.template_key,
        species        = template.species,
        reminder_days  = body.reminder_days,
        notify_channels= body.notify_channels,
        db             = db,
    )

    return {
        "schedule_name":  body.schedule_name,
        "template":       template.name,
        "events_created": len(created),
        "events":         [_event_to_dict(e) for e in created],
    }


@sched_router.get("")
async def list_events(
    farm_id:   Optional[str] = None,
    species:   Optional[str] = None,
    completed: bool          = False,
    days:      int           = Query(default=90, ge=1, le=365),
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """List upcoming scheduled events."""
    deadline = datetime.utcnow() + timedelta(days=days)
    filters  = [
        ScheduledEvent.user_id   == user.id,
        ScheduledEvent.completed == completed,
        ScheduledEvent.event_date <= deadline,
    ]
    if farm_id: filters.append(ScheduledEvent.farm_id == farm_id)
    if species: filters.append(ScheduledEvent.species == species)

    result = await db.execute(
        select(ScheduledEvent)
        .where(and_(*filters))
        .order_by(ScheduledEvent.event_date)
    )
    events = result.scalars().all()
    return [_event_to_dict(e) for e in events]


@sched_router.get("/today")
async def events_today(
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Events due today and overdue events."""
    now   = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tmrw  = today + timedelta(days=1)

    result = await db.execute(
        select(ScheduledEvent).where(
            ScheduledEvent.user_id   == user.id,
            ScheduledEvent.completed == False,
            ScheduledEvent.event_date < tmrw,
        ).order_by(ScheduledEvent.event_date)
    )
    events = result.scalars().all()

    today_events    = [e for e in events if e.event_date >= today]
    overdue_events  = [e for e in events if e.event_date < today]

    return {
        "today":   [_event_to_dict(e) for e in today_events],
        "overdue": [_event_to_dict(e) for e in overdue_events],
        "total":   len(events),
    }


@sched_router.get("/{event_id}")
async def get_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScheduledEvent).where(ScheduledEvent.id == event_id, ScheduledEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found.")
    return _event_to_dict(event)


@sched_router.put("/{event_id}")
async def update_event(
    event_id: str,
    body: UpdateEventRequest,
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScheduledEvent).where(ScheduledEvent.id == event_id, ScheduledEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found.")

    if body.event_date:
        try:
            event.event_date = datetime.fromisoformat(body.event_date)
        except ValueError:
            raise HTTPException(422, "Invalid date format.")
    if body.reminder_days  is not None: event.reminder_days   = ",".join(str(d) for d in body.reminder_days)
    if body.notify_channels is not None: event.notify_channels = ",".join(body.notify_channels)
    if body.title          is not None: event.title           = body.title
    if body.description    is not None: event.description     = body.description

    event.status = EventStatus.PENDING  # reset so rescheduled event gets re-notified
    await db.flush()
    return _event_to_dict(event)


@sched_router.post("/{event_id}/complete")
async def complete_event(
    event_id: str,
    body: CompleteEventRequest,
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScheduledEvent).where(ScheduledEvent.id == event_id, ScheduledEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found.")

    event.completed        = True
    event.completed_at     = datetime.utcnow()
    event.completion_notes = body.notes
    event.status           = EventStatus.DISMISSED
    await db.flush()
    return {"id": event.id, "completed": True, "completed_at": event.completed_at}


@sched_router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScheduledEvent).where(ScheduledEvent.id == event_id, ScheduledEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found.")
    await db.delete(event)


# ─── Push token registration ──────────────────────────────────────────────────

@sched_router.post("/push-token", status_code=201)
async def register_push_token(
    body: PushTokenRequest,
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Register an Expo push token for this device."""
    # Upsert — update if token exists
    result = await db.execute(select(PushToken).where(PushToken.token == body.token))
    existing = result.scalar_one_or_none()

    if existing:
        existing.user_id     = user.id
        existing.device_name = body.device_name
        existing.platform    = body.platform
        existing.is_active   = True
        existing.last_used   = datetime.utcnow()
    else:
        token_row = PushToken(
            id          = str(uuid.uuid4()),
            user_id     = user.id,
            token       = body.token,
            device_name = body.device_name,
            platform    = body.platform,
        )
        db.add(token_row)

    await db.flush()
    return {"registered": True, "token": body.token[:20] + "..."}


@sched_router.delete("/push-token")
async def unregister_push_token(
    token: str,
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Unregister push token (e.g. on logout)."""
    result = await db.execute(
        select(PushToken).where(PushToken.token == token, PushToken.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row:
        row.is_active = False
        await db.flush()
    return {"unregistered": True}