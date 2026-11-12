"""
src/digest/schemas.py
─────────────────────
Pydantic v2 schemas for the Weekly Recognition Digest.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class TopPerformer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    username: str
    count: int


class WeeklyDigestData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    week_start: datetime
    week_end: datetime
    total_recognitions: int
    total_points_awarded: float
    unique_givers: int
    unique_receivers: int
    top_giver: TopPerformer | None = None
    top_receiver: TopPerformer | None = None


class DigestEmailRequest(BaseModel):
    """
    Trigger a weekly digest email for a specific manager[cite: 36].

    manager_id — UUID of the manager to scope the digest to[cite: 36].
                 When omitted, covers platform-wide data[cite: 36].
    week_start — Monday 00:00 UTC; defaults to last completed week[cite: 36].
    """
    model_config = ConfigDict(extra="forbid")

    manager_email: EmailStr
    manager_id: UUID | None = None
    week_start: datetime | None = None


class DigestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    success: bool
    message: str
    data: WeeklyDigestData | None = None