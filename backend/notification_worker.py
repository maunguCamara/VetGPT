"""
vetgpt/backend/notification_worker.py

Background notification worker using APScheduler.

Runs as part of the FastAPI process — no separate service needed.
Checks every hour for events needing reminders and fires:
  - Expo push notifications (mobile)
  - Telegram messages (via bot)
  - WhatsApp messages (via Twilio)

APScheduler runs in the background thread pool — does not block the API.

Install:
  pip install apscheduler
"""

import os
import logging
from datetime import datetime, timedelta

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from .config import get_settings
from .schedule_models import ScheduledEvent, PushToken, NotificationLog, EventStatus, NotificationChannel

log      = logging.getLogger(__name__)
settings = get_settings()

# ── DB session for background worker ─────────────────────────────────────────

engine        = create_async_engine(settings.database_url, echo=False)
AsyncWorkerSession = async_sessionmaker(engine, expire_on_commit=False)


# ── Expo Push Notifications ───────────────────────────────────────────────────

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

async def send_expo_push(tokens: list[str], title: str, body: str, data: dict = None) -> list[dict]:
    """
    Send push notifications to a list of Expo push tokens.
    Batches up to 100 per request (Expo limit).
    Returns list of receipts.
    """
    if not tokens:
        return []

    messages = [
        {
            "to":    token,
            "title": title,
            "body":  body,
            "data":  data or {},
            "sound": "default",
            "priority": "high" if data and data.get("is_critical") else "normal",
            "badge": 1,
            "_displayInForeground": True,
        }
        for token in tokens
        if token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")
    ]

    if not messages:
        return []

    receipts = []
    # Batch in groups of 100
    for i in range(0, len(messages), 100):
        batch = messages[i:i+100]
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    EXPO_PUSH_URL,
                    json=batch,
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                )
                resp.raise_for_status()
                receipts.extend(resp.json().get("data", []))
        except Exception as e:
            log.error(f"[Push] Batch send failed: {e}")

    return receipts


# ── Telegram notification ─────────────────────────────────────────────────────

async def send_telegram_notification(chat_id: str, message: str) -> bool:
    """Send a notification message to a Telegram chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            )
            return resp.status_code == 200
    except Exception as e:
        log.error(f"[Telegram] Notification failed: {e}")
        return False


# ── WhatsApp notification ─────────────────────────────────────────────────────

async def send_whatsapp_notification(phone: str, message: str) -> bool:
    """Send a WhatsApp notification via Twilio."""
    sid   = os.getenv("TWILIO_ACCOUNT_SID",  "")
    token = os.getenv("TWILIO_AUTH_TOKEN",   "")
    from_ = os.getenv("TWILIO_WHATSAPP_FROM","")
    if not all([sid, token, from_]):
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data={"From": from_, "To": f"whatsapp:{phone}", "Body": message},
                auth=(sid, token),
            )
            return resp.status_code in (200, 201)
    except Exception as e:
        log.error(f"[WhatsApp] Notification failed: {e}")
        return False


# ── Message formatter ─────────────────────────────────────────────────────────

def format_reminder(event: ScheduledEvent, days_until: int) -> tuple[str, str]:
    """
    Returns (title, body) for the notification.
    Adjusts urgency language based on how far away the event is.
    """
    if days_until == 0:
        urgency = "📅 TODAY"
    elif days_until == 1:
        urgency = "⏰ TOMORROW"
    elif days_until <= 3:
        urgency = f"🔔 In {days_until} days"
    else:
        urgency = f"📌 Reminder — {days_until} days"

    critical_prefix = "🚨 CRITICAL: " if event.is_critical else ""
    title = f"{critical_prefix}{urgency}: {event.schedule_name}"
    body  = (
        f"{event.title}\n\n"
        f"📅 Date: {event.event_date.strftime('%d %b %Y')}\n"
        f"{event.description[:200]}{'...' if len(event.description) > 200 else ''}"
    )
    return title, body


def format_telegram_message(event: ScheduledEvent, days_until: int) -> str:
    """Format Telegram-flavoured markdown notification."""
    title, body = format_reminder(event, days_until)
    return (
        f"*{title}*\n\n"
        f"{body}\n\n"
        f"_Reply with 'done {event.id[:8]}' to mark as complete_"
    )


# ── Core worker ───────────────────────────────────────────────────────────────

async def check_and_send_notifications():
    """
    Main worker function — runs on schedule.

    Logic:
    1. Find all pending events where today matches a reminder_day
    2. For each event, gather user's push tokens + bot IDs
    3. Send notifications via configured channels
    4. Log results
    """
    log.info("[Worker] Checking for due notifications...")
    now   = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with AsyncWorkerSession() as db:
        # Get all incomplete pending events in the next 30 days
        result = await db.execute(
            select(ScheduledEvent).where(
                and_(
                    ScheduledEvent.completed == False,
                    ScheduledEvent.status.in_([EventStatus.PENDING, EventStatus.SNOOZED]),
                    ScheduledEvent.event_date >= today,
                    ScheduledEvent.event_date <= today + timedelta(days=30),
                )
            )
        )
        events = result.scalars().all()
        log.info(f"[Worker] Found {len(events)} upcoming events to check")

        notified = 0
        for event in events:
            days_until = (event.event_date.replace(hour=0,minute=0,second=0,microsecond=0) - today).days

            # Check if today is a reminder day for this event
            reminder_days = [int(d) for d in event.reminder_days.split(",") if d.strip()]
            if days_until not in reminder_days:
                continue

            # Avoid double-notifying on same day
            if event.last_notified:
                last = event.last_notified.replace(hour=0,minute=0,second=0,microsecond=0)
                if last == today:
                    continue

            channels = event.notify_channels.split(",")
            title, body = format_reminder(event, days_until)

            # ── Push notifications ────────────────────────────────────────────
            if "push" in channels:
                tokens_result = await db.execute(
                    select(PushToken).where(
                        PushToken.user_id  == event.user_id,
                        PushToken.is_active == True,
                    )
                )
                tokens = [t.token for t in tokens_result.scalars().all()]
                if tokens:
                    receipts = await send_expo_push(
                        tokens = tokens,
                        title  = title,
                        body   = body,
                        data   = {
                            "event_id":    event.id,
                            "is_critical": event.is_critical,
                            "screen":      "schedules",
                        },
                    )
                    for i, receipt in enumerate(receipts):
                        success = receipt.get("status") == "ok"
                        log_entry = NotificationLog(
                            event_id  = event.id,
                            user_id   = event.user_id,
                            channel   = NotificationChannel.PUSH,
                            recipient = tokens[i] if i < len(tokens) else "",
                            message   = body,
                            success   = success,
                            error     = receipt.get("message", "") if not success else "",
                        )
                        db.add(log_entry)

            # ── Telegram ──────────────────────────────────────────────────────
            if "telegram" in channels:
                # Look up telegram chat_id from user_data store
                # In production store this in DB when user first messages the bot
                telegram_chat_id = await _get_user_telegram_id(event.user_id, db)
                if telegram_chat_id:
                    message = format_telegram_message(event, days_until)
                    success = await send_telegram_notification(telegram_chat_id, message)
                    log_entry = NotificationLog(
                        event_id  = event.id,
                        user_id   = event.user_id,
                        channel   = NotificationChannel.TELEGRAM,
                        recipient = telegram_chat_id,
                        message   = message,
                        success   = success,
                    )
                    db.add(log_entry)

            # ── WhatsApp ──────────────────────────────────────────────────────
            if "whatsapp" in channels:
                phone = await _get_user_phone(event.user_id, db)
                if phone:
                    _, wa_body = format_reminder(event, days_until)
                    success = await send_whatsapp_notification(phone, f"*{title}*\n\n{wa_body}")
                    log_entry = NotificationLog(
                        event_id  = event.id,
                        user_id   = event.user_id,
                        channel   = NotificationChannel.WHATSAPP,
                        recipient = phone,
                        message   = wa_body,
                        success   = success,
                    )
                    db.add(log_entry)

            # Update event notification tracking
            event.last_notified      = now
            event.notification_count += 1

            notified += 1

        await db.commit()
        log.info(f"[Worker] Sent notifications for {notified} events")


async def _get_user_telegram_id(user_id: str, db: AsyncSession) -> str | None:
    """
    Retrieve stored Telegram chat_id for a user.
    Stored when user first interacts with the bot and identifies themselves.
    """
    # Import here to avoid circular imports
    from .database import User
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if user:
        return getattr(user, "telegram_chat_id", None)
    return None


async def _get_user_phone(user_id: str, db: AsyncSession) -> str | None:
    """Retrieve stored WhatsApp phone number for a user."""
    from .database import User
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if user:
        return getattr(user, "phone_number", None)
    return None


# ── Scheduler setup ───────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler(timezone="Africa/Nairobi")


def start_scheduler():
    """
    Start the APScheduler background worker.
    Called from main.py lifespan on startup.

    Jobs:
      - Hourly check at :05 past each hour (avoids midnight race conditions)
      - Daily morning digest at 07:00 EAT
    """
    # Main notification check — every hour
    scheduler.add_job(
        check_and_send_notifications,
        trigger  = CronTrigger(minute=5),   # fires at :05 past every hour
        id       = "notification_check",
        name     = "Check and send due notifications",
        replace_existing = True,
        misfire_grace_time = 300,           # 5 min grace if server was down
    )

    # Morning digest — 7am Nairobi time
    scheduler.add_job(
        send_morning_digest,
        trigger  = CronTrigger(hour=7, minute=0),
        id       = "morning_digest",
        name     = "Daily morning schedule digest",
        replace_existing = True,
    )

    scheduler.start()
    log.info("[Worker] APScheduler started — notification worker running")


def stop_scheduler():
    """Stop scheduler gracefully on shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("[Worker] APScheduler stopped")


async def send_morning_digest():
    """
    Send a daily morning summary of events due in the next 7 days
    to users who have events today or tomorrow.
    Only sent if user has events due within 24 hours.
    """
    now   = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tmrw  = today + timedelta(days=1)

    async with AsyncWorkerSession() as db:
        # Find events due today or tomorrow across all users
        result = await db.execute(
            select(ScheduledEvent).where(
                and_(
                    ScheduledEvent.completed == False,
                    ScheduledEvent.event_date >= today,
                    ScheduledEvent.event_date < tmrw + timedelta(days=1),
                )
            ).order_by(ScheduledEvent.user_id, ScheduledEvent.event_date)
        )
        events = result.scalars().all()

        # Group by user
        by_user: dict[str, list[ScheduledEvent]] = {}
        for e in events:
            by_user.setdefault(e.user_id, []).append(e)

        for user_id, user_events in by_user.items():
            today_events = [e for e in user_events if e.event_date < tmrw]
            tmrw_events  = [e for e in user_events if e.event_date >= tmrw]

            lines = ["🌅 *Good morning — your VetGPT schedule for today:*\n"]
            if today_events:
                lines.append("*Today:*")
                for e in today_events:
                    critical = "🚨 " if e.is_critical else "✅ "
                    lines.append(f"{critical}{e.title}")
            if tmrw_events:
                lines.append("\n*Tomorrow:*")
                for e in tmrw_events:
                    lines.append(f"📅 {e.title}")

            message = "\n".join(lines)

            # Send push
            tokens_r = await db.execute(
                select(PushToken).where(PushToken.user_id == user_id, PushToken.is_active == True)
            )
            tokens = [t.token for t in tokens_r.scalars().all()]
            if tokens:
                await send_expo_push(
                    tokens = tokens,
                    title  = f"📋 {len(today_events)} tasks due today",
                    body   = "\n".join(e.title for e in today_events[:3]),
                    data   = {"screen": "schedules"},
                )

        log.info(f"[Worker] Morning digest sent to {len(by_user)} users")