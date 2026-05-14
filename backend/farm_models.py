"""
vetgpt/backend/farm_models.py

Farm management database models.

Tables:
  farms            — farm name, owner, location, species kept
  animals          — individual animals with tag numbers
  treatment_records — treatment events with follow-up notes
  audio_notes      — voice recordings transcribed to text
"""

import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, String, Integer, Float, DateTime,
    Boolean, Text, ForeignKey, Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from .database import Base


class AnimalSpecies(str, Enum):
    CATTLE   = "cattle"
    SHEEP    = "sheep"
    GOAT     = "goat"
    PIG      = "pig"
    POULTRY  = "poultry"
    DOG      = "dog"
    CAT      = "cat"
    HORSE    = "horse"
    RABBIT   = "rabbit"
    OTHER    = "other"


class TreatmentOutcome(str, Enum):
    IMPROVED   = "improved"
    RECOVERED  = "recovered"
    NO_CHANGE  = "no_change"
    WORSENED   = "worsened"
    DIED       = "died"
    PENDING    = "pending"


class Farm(Base):
    __tablename__ = "farms"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id   = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name       = Column(String(255), nullable=False)
    location   = Column(String(500), default="")
    notes      = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    animals   = relationship("Animal",          back_populates="farm", cascade="all, delete-orphan")
    treatments = relationship("TreatmentRecord", back_populates="farm", cascade="all, delete-orphan")


class Animal(Base):
    __tablename__ = "animals"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    farm_id    = Column(String(36), ForeignKey("farms.id"), nullable=False, index=True)
    tag_number = Column(String(100), default="")     # ear tag, microchip, brand
    name       = Column(String(255), default="")     # optional name
    species    = Column(SAEnum(AnimalSpecies), default=AnimalSpecies.CATTLE)
    breed      = Column(String(255), default="")
    sex        = Column(String(10), default="")      # male, female, unknown
    dob        = Column(DateTime, nullable=True)     # date of birth
    weight_kg  = Column(Float, nullable=True)
    notes      = Column(Text, default="")
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    farm       = relationship("Farm", back_populates="animals")
    treatments = relationship("TreatmentRecord", back_populates="animal", cascade="all, delete-orphan")


class TreatmentRecord(Base):
    __tablename__ = "treatment_records"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    farm_id          = Column(String(36), ForeignKey("farms.id"),   nullable=False, index=True)
    animal_id        = Column(String(36), ForeignKey("animals.id"), nullable=True,  index=True)
    recorded_by      = Column(String(36), ForeignKey("users.id"),   nullable=False)

    # Treatment details
    treatment_date   = Column(DateTime, default=datetime.utcnow, index=True)
    number_of_animals= Column(Integer, default=1)        # for herd treatments
    diagnosis        = Column(Text, default="")          # presenting complaint / diagnosis
    treatment_given  = Column(Text, nullable=False)      # drug name, procedure
    dosage           = Column(String(500), default="")   # e.g. "10ml/kg IM"
    route            = Column(String(100), default="")   # oral, IM, IV, SC, topical
    withdrawal_days  = Column(Integer, nullable=True)    # meat/milk withdrawal period

    # Follow-up
    follow_up_date   = Column(DateTime, nullable=True)
    outcome          = Column(SAEnum(TreatmentOutcome), default=TreatmentOutcome.PENDING)
    follow_up_notes  = Column(Text, default="")          # was there improvement?
    next_action      = Column(Text, default="")          # vet referral, repeat treatment etc.

    # Audio note
    audio_transcript = Column(Text, default="")          # transcribed voice note
    audio_language   = Column(String(10), default="en")  # language of the audio

    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farm             = relationship("Farm",   back_populates="treatments")
    animal           = relationship("Animal", back_populates="treatments")
