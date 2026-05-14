"""
vetgpt/backend/farm_routes.py

Farm management API — CRUD for farms, animals, treatment records, audio notes.
"""

import csv
import io
import uuid
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, status,
    UploadFile, File, Form, Query,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .database import get_db, User
from .farm_models import Farm, Animal, TreatmentRecord, AnimalSpecies, TreatmentOutcome

farm_router = APIRouter(prefix="/api/farms", tags=["farm management"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class FarmCreate(BaseModel):
    name:     str
    location: str = ""
    notes:    str = ""

class FarmUpdate(BaseModel):
    name:     Optional[str] = None
    location: Optional[str] = None
    notes:    Optional[str] = None

class AnimalCreate(BaseModel):
    tag_number: str = ""
    name:       str = ""
    species:    AnimalSpecies = AnimalSpecies.CATTLE
    breed:      str = ""
    sex:        str = ""
    weight_kg:  Optional[float] = None
    notes:      str = ""

class AnimalUpdate(BaseModel):
    tag_number: Optional[str]          = None
    name:       Optional[str]          = None
    species:    Optional[AnimalSpecies]= None
    breed:      Optional[str]          = None
    sex:        Optional[str]          = None
    weight_kg:  Optional[float]        = None
    notes:      Optional[str]          = None
    is_active:  Optional[bool]         = None

class TreatmentCreate(BaseModel):
    animal_id:          Optional[str]   = None
    treatment_date:     Optional[str]   = None
    number_of_animals:  int             = 1
    diagnosis:          str             = ""
    treatment_given:    str
    dosage:             str             = ""
    route:              str             = ""
    withdrawal_days:    Optional[int]   = None
    follow_up_date:     Optional[str]   = None
    follow_up_notes:    str             = ""
    outcome:            TreatmentOutcome = TreatmentOutcome.PENDING
    next_action:        str             = ""
    audio_transcript:   str             = ""
    audio_language:     str             = "en"

class TreatmentUpdate(BaseModel):
    diagnosis:          Optional[str]              = None
    treatment_given:    Optional[str]              = None
    dosage:             Optional[str]              = None
    route:              Optional[str]              = None
    withdrawal_days:    Optional[int]              = None
    follow_up_date:     Optional[str]              = None
    follow_up_notes:    Optional[str]              = None
    outcome:            Optional[TreatmentOutcome] = None
    next_action:        Optional[str]              = None
    audio_transcript:   Optional[str]              = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def get_farm_or_404(farm_id: str, user: User, db: AsyncSession) -> Farm:
    result = await db.execute(
        select(Farm).where(Farm.id == farm_id, Farm.owner_id == user.id)
    )
    farm = result.scalar_one_or_none()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found.")
    return farm

def parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid date: {s}. Use ISO 8601.")


# ─── Farms ────────────────────────────────────────────────────────────────────

@farm_router.post("", status_code=201)
async def create_farm(
    body: FarmCreate,
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    farm = Farm(id=str(uuid.uuid4()), owner_id=user.id,
                name=body.name, location=body.location, notes=body.notes)
    db.add(farm)
    await db.flush()
    return {"id": farm.id, "name": farm.name, "location": farm.location, "created_at": farm.created_at}


@farm_router.get("")
async def list_farms(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Farm).where(Farm.owner_id == user.id).order_by(Farm.created_at.desc()))
    farms  = result.scalars().all()
    return [{"id": f.id, "name": f.name, "location": f.location, "created_at": f.created_at} for f in farms]


@farm_router.get("/{farm_id}")
async def get_farm(farm_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    farm   = await get_farm_or_404(farm_id, user, db)
    result = await db.execute(select(Animal).where(Animal.farm_id == farm_id, Animal.is_active == True))
    return {
        "id": farm.id, "name": farm.name, "location": farm.location,
        "notes": farm.notes, "created_at": farm.created_at,
        "animal_count": len(result.scalars().all()),
    }


@farm_router.put("/{farm_id}")
async def update_farm(farm_id: str, body: FarmUpdate,
                      user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    farm = await get_farm_or_404(farm_id, user, db)
    if body.name     is not None: farm.name     = body.name
    if body.location is not None: farm.location = body.location
    if body.notes    is not None: farm.notes    = body.notes
    await db.flush()
    return {"id": farm.id, "name": farm.name, "updated": True}


@farm_router.delete("/{farm_id}", status_code=204)
async def delete_farm(farm_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    farm = await get_farm_or_404(farm_id, user, db)
    await db.delete(farm)


# ─── Animals ──────────────────────────────────────────────────────────────────

@farm_router.post("/{farm_id}/animals", status_code=201)
async def add_animal(farm_id: str, body: AnimalCreate,
                     user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_farm_or_404(farm_id, user, db)
    animal = Animal(id=str(uuid.uuid4()), farm_id=farm_id, tag_number=body.tag_number,
                    name=body.name, species=body.species, breed=body.breed,
                    sex=body.sex, weight_kg=body.weight_kg, notes=body.notes)
    db.add(animal)
    await db.flush()
    return {"id": animal.id, "tag_number": animal.tag_number, "species": animal.species.value}


@farm_router.get("/{farm_id}/animals")
async def list_animals(farm_id: str, species: Optional[str] = None, active: bool = True,
                       user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_farm_or_404(farm_id, user, db)
    filters = [Animal.farm_id == farm_id, Animal.is_active == active]
    if species:
        filters.append(Animal.species == species)
    result  = await db.execute(select(Animal).where(and_(*filters)).order_by(Animal.tag_number))
    animals = result.scalars().all()
    return [{"id": a.id, "tag_number": a.tag_number, "name": a.name,
             "species": a.species.value, "breed": a.breed, "sex": a.sex,
             "weight_kg": a.weight_kg, "notes": a.notes} for a in animals]


@farm_router.put("/{farm_id}/animals/{animal_id}")
async def update_animal(farm_id: str, animal_id: str, body: AnimalUpdate,
                        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_farm_or_404(farm_id, user, db)
    result = await db.execute(select(Animal).where(Animal.id == animal_id, Animal.farm_id == farm_id))
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found.")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(animal, k, v)
    await db.flush()
    return {"id": animal.id, "updated": True}


@farm_router.delete("/{farm_id}/animals/{animal_id}", status_code=204)
async def remove_animal(farm_id: str, animal_id: str,
                        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_farm_or_404(farm_id, user, db)
    result = await db.execute(select(Animal).where(Animal.id == animal_id, Animal.farm_id == farm_id))
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found.")
    animal.is_active = False   # soft delete — keeps treatment history
    await db.flush()


# ─── Treatments ───────────────────────────────────────────────────────────────

@farm_router.post("/{farm_id}/treatments", status_code=201)
async def log_treatment(farm_id: str, body: TreatmentCreate,
                        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_farm_or_404(farm_id, user, db)
    record = TreatmentRecord(
        id=str(uuid.uuid4()), farm_id=farm_id, animal_id=body.animal_id,
        recorded_by=user.id,
        treatment_date=parse_date(body.treatment_date) or datetime.utcnow(),
        number_of_animals=body.number_of_animals,
        diagnosis=body.diagnosis, treatment_given=body.treatment_given,
        dosage=body.dosage, route=body.route, withdrawal_days=body.withdrawal_days,
        follow_up_date=parse_date(body.follow_up_date),
        follow_up_notes=body.follow_up_notes, outcome=body.outcome,
        next_action=body.next_action, audio_transcript=body.audio_transcript,
        audio_language=body.audio_language,
    )
    db.add(record)
    await db.flush()
    return {"id": record.id, "treatment_date": record.treatment_date, "created": True}


@farm_router.get("/{farm_id}/treatments")
async def list_treatments(farm_id: str, animal_id: Optional[str] = None,
                          limit: int = Query(default=50, ge=1, le=200),
                          offset: int = Query(default=0, ge=0),
                          user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_farm_or_404(farm_id, user, db)
    filters = [TreatmentRecord.farm_id == farm_id]
    if animal_id:
        filters.append(TreatmentRecord.animal_id == animal_id)
    result  = await db.execute(
        select(TreatmentRecord).where(and_(*filters))
        .order_by(TreatmentRecord.treatment_date.desc()).limit(limit).offset(offset)
    )
    records = result.scalars().all()
    return [
        {"id": r.id, "animal_id": r.animal_id, "treatment_date": r.treatment_date,
         "number_of_animals": r.number_of_animals, "diagnosis": r.diagnosis,
         "treatment_given": r.treatment_given, "dosage": r.dosage, "route": r.route,
         "withdrawal_days": r.withdrawal_days, "follow_up_date": r.follow_up_date,
         "follow_up_notes": r.follow_up_notes, "outcome": r.outcome.value if r.outcome else None,
         "next_action": r.next_action, "audio_transcript": r.audio_transcript}
        for r in records
    ]


@farm_router.put("/{farm_id}/treatments/{treatment_id}")
async def update_treatment(farm_id: str, treatment_id: str, body: TreatmentUpdate,
                           user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_farm_or_404(farm_id, user, db)
    result = await db.execute(
        select(TreatmentRecord).where(TreatmentRecord.id == treatment_id, TreatmentRecord.farm_id == farm_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Treatment record not found.")
    data = body.model_dump(exclude_none=True)
    if "follow_up_date" in data:
        data["follow_up_date"] = parse_date(data["follow_up_date"])
    for k, v in data.items():
        setattr(record, k, v)
    await db.flush()
    return {"id": record.id, "updated": True}


@farm_router.delete("/{farm_id}/treatments/{treatment_id}", status_code=204)
async def delete_treatment(farm_id: str, treatment_id: str,
                           user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_farm_or_404(farm_id, user, db)
    result = await db.execute(
        select(TreatmentRecord).where(TreatmentRecord.id == treatment_id, TreatmentRecord.farm_id == farm_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    await db.delete(record)


# ─── Audio transcription ──────────────────────────────────────────────────────

@farm_router.post("/{farm_id}/treatments/{treatment_id}/audio")
async def upload_audio_note(
    farm_id: str, treatment_id: str,
    file:     UploadFile = File(...),
    language: str        = Form(default="en"),
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Transcribe voice note and attach to treatment record. Supports en, sw, fr, ar, pt, es, zh."""
    await get_farm_or_404(farm_id, user, db)
    result = await db.execute(
        select(TreatmentRecord).where(TreatmentRecord.id == treatment_id, TreatmentRecord.farm_id == farm_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Treatment record not found.")

    allowed = {"audio/mpeg","audio/mp4","audio/m4a","audio/wav","audio/ogg","audio/webm","audio/x-m4a"}
    if (file.content_type or "") not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")

    audio_bytes = await file.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio file is empty.")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio too large. Max 25 MB.")

    transcript = await _transcribe(audio_bytes, file.content_type or "audio/mpeg", language)
    record.audio_transcript = transcript
    record.audio_language   = language
    await db.flush()
    return {"transcript": transcript, "language": language, "word_count": len(transcript.split())}


async def _transcribe(audio_bytes: bytes, mime_type: str, language: str) -> str:
    """Try faster-whisper (local) first, fall back to OpenAI Whisper."""
    from .config import get_settings
    settings = get_settings()

    try:
        import tempfile, asyncio
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            segments, _ = model.transcribe(tmp_path, language=language, beam_size=5)
            return " ".join(s.text for s in segments).strip()
        finally:
            os.unlink(tmp_path)
    except Exception:
        pass

    if settings.openai_api_key:
        import httpx
        ext_map = {"audio/mpeg":".mp3","audio/mp4":".mp4","audio/m4a":".m4a",
                   "audio/x-m4a":".m4a","audio/wav":".wav","audio/ogg":".ogg","audio/webm":".webm"}
        ext = ext_map.get(mime_type, ".mp3")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                files={"file": (f"audio{ext}", audio_bytes, mime_type)},
                data={"model": "whisper-1", "language": language},
            )
            resp.raise_for_status()
            return resp.json().get("text", "")

    raise HTTPException(status_code=503, detail=(
        "Transcription not configured.\n"
        "Option 1 (free local): pip install faster-whisper\n"
        "Option 2 (cloud): set OPENAI_API_KEY in .env"
    ))


# ─── Upcoming follow-ups ──────────────────────────────────────────────────────

@farm_router.get("/treatments/upcoming-followups")
async def upcoming_followups(days: int = Query(default=7, ge=1, le=90),
                             user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now      = datetime.utcnow()
    deadline = now + timedelta(days=days)
    farms_r  = await db.execute(select(Farm.id).where(Farm.owner_id == user.id))
    farm_ids = [r[0] for r in farms_r.fetchall()]
    if not farm_ids:
        return []
    result = await db.execute(
        select(TreatmentRecord).where(
            TreatmentRecord.farm_id.in_(farm_ids),
            TreatmentRecord.follow_up_date >= now,
            TreatmentRecord.follow_up_date <= deadline,
            TreatmentRecord.outcome == TreatmentOutcome.PENDING,
        ).order_by(TreatmentRecord.follow_up_date)
    )
    return [
        {"id": r.id, "farm_id": r.farm_id, "animal_id": r.animal_id,
         "treatment_given": r.treatment_given, "follow_up_date": r.follow_up_date,
         "days_remaining": (r.follow_up_date - now).days, "diagnosis": r.diagnosis}
        for r in result.scalars().all()
    ]


# ─── CSV export ───────────────────────────────────────────────────────────────

@farm_router.get("/{farm_id}/treatments/export")
async def export_csv(farm_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    farm   = await get_farm_or_404(farm_id, user, db)
    result = await db.execute(
        select(TreatmentRecord).where(TreatmentRecord.farm_id == farm_id)
        .order_by(TreatmentRecord.treatment_date.desc())
    )
    records = result.scalars().all()
    output  = io.StringIO()
    writer  = csv.writer(output)
    writer.writerow(["Date","Animal","No.Animals","Diagnosis","Treatment","Dosage",
                     "Route","Withdrawal Days","Follow-up Date","Outcome","Follow-up Notes",
                     "Next Action","Voice Note"])
    for r in records:
        writer.writerow([
            r.treatment_date.strftime("%Y-%m-%d") if r.treatment_date else "",
            r.animal_id or "Herd", r.number_of_animals, r.diagnosis,
            r.treatment_given, r.dosage, r.route, r.withdrawal_days or "",
            r.follow_up_date.strftime("%Y-%m-%d") if r.follow_up_date else "",
            r.outcome.value if r.outcome else "", r.follow_up_notes,
            r.next_action, r.audio_transcript,
        ])
    output.seek(0)
    fname = f"{farm.name.replace(' ','_')}_treatments.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})
