"""
vetgpt/backend/schedule_models.py

Database models for scheduled events and push notifications.
"""

import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from .database import Base


class EventStatus(str, Enum):
    PENDING   = "pending"
    SENT      = "sent"
    SNOOZED   = "snoozed"
    DISMISSED = "dismissed"
    FAILED    = "failed"


class NotificationChannel(str, Enum):
    PUSH      = "push"       # Expo push notifications
    TELEGRAM  = "telegram"
    WHATSAPP  = "whatsapp"


class ScheduledEvent(Base):
    """
    A single event in a schedule — e.g. 'Day 7 Newcastle vaccine'.
    Generated either from a template or by the LLM from natural language.
    """
    __tablename__ = "scheduled_events"

    id              = Column(String(36),  primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id         = Column(String(36),  ForeignKey("users.id"), nullable=False, index=True)
    farm_id         = Column(String(36),  ForeignKey("farms.id"), nullable=True,  index=True)
    animal_id       = Column(String(36),  ForeignKey("animals.id"), nullable=True)

    # Schedule context
    schedule_name   = Column(String(255), nullable=False)   # e.g. "Chick Vaccination — Batch A"
    template_key    = Column(String(100), default="")       # e.g. "chick_vaccination"
    species         = Column(String(50),  default="")

    # Event details
    title           = Column(String(500), nullable=False)
    description     = Column(Text,        default="")
    event_date      = Column(DateTime,    nullable=False, index=True)
    is_critical     = Column(Boolean,     default=False)

    # Notification preferences
    reminder_days   = Column(String(100), default="1,0")    # comma-separated: "3,1,0"
    notify_channels = Column(String(100), default="push")   # comma-separated

    # Status
    status          = Column(SAEnum(EventStatus), default=EventStatus.PENDING)
    last_notified   = Column(DateTime, nullable=True)
    notification_count = Column(Integer, default=0)

    # Completion
    completed       = Column(Boolean,  default=False)
    completed_at    = Column(DateTime, nullable=True)
    completion_notes= Column(Text,     default="")

    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    notifications   = relationship("NotificationLog", back_populates="event", cascade="all, delete-orphan")


class PushToken(Base):
    """
    Expo push notification token for a user's device.
    A user can have multiple devices.
    """
    __tablename__ = "push_tokens"

    id          = Column(String(36),  primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String(36),  ForeignKey("users.id"), nullable=False, index=True)
    token       = Column(String(500), nullable=False, unique=True)
    device_name = Column(String(255), default="")
    platform    = Column(String(20),  default="")    # ios, android
    is_active   = Column(Boolean,     default=True)
    created_at  = Column(DateTime,    default=datetime.utcnow)
    last_used   = Column(DateTime,    nullable=True)


class NotificationLog(Base):
    """
    Record of every notification sent — for debugging and auditing.
    """
    __tablename__ = "notification_logs"

    id         = Column(String(36),  primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id   = Column(String(36),  ForeignKey("scheduled_events.id"), nullable=False, index=True)
    user_id    = Column(String(36),  ForeignKey("users.id"), nullable=False)
    channel    = Column(SAEnum(NotificationChannel), nullable=False)
    recipient  = Column(String(500), default="")     # push token, telegram chat_id, phone number
    message    = Column(Text,        default="")
    success    = Column(Boolean,     default=True)
    error      = Column(Text,        default="")
    sent_at    = Column(DateTime,    default=datetime.utcnow)

    event      = relationship("ScheduledEvent", back_populates="notifications")