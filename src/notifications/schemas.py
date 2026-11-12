"""
src/notifications/schemas.py
────────────────────────────
Pydantic v2 schemas for in-app, email, and Slack notifications.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationType(str, Enum):
    REVIEW = "REVIEW"
    REWARD = "REWARD"
    REWARD_REDEEMED = "REWARD_REDEEMED"
    POINTS_CREDIT = "POINTS_CREDIT"
    SYSTEM = "SYSTEM"
    CELEBRATION = "CELEBRATION"
    ANNOUNCEMENT = "ANNOUNCEMENT"


class CelebrationType(str, Enum):
    BIRTHDAY = "BIRTHDAY"
    WORK_ANNIVERSARY = "WORK_ANNIVERSARY"


# ══════════════════════════════════════════════════════════════
#  Requests
# ══════════════════════════════════════════════════════════════

class NotificationCreateRequest(BaseModel):
    """
    Send a notification to one or more specific employees.
    Manual sends are restricted to REVIEW, REWARD, and SYSTEM.
    """
    model_config = ConfigDict(extra="forbid")

    employee_ids: list[UUID]
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    type: NotificationType = NotificationType.SYSTEM

    @field_validator("type")
    @classmethod
    def restrict_manual_types(cls, v: NotificationType) -> NotificationType:
        reserved = {
            NotificationType.CELEBRATION,
            NotificationType.ANNOUNCEMENT,
            NotificationType.REWARD_REDEEMED,
            NotificationType.POINTS_CREDIT,
        }
        if v in reserved:
            raise ValueError(
                f"Type '{v.value}' cannot be sent via this endpoint. "
                "Use POST /notifications/announcements for ANNOUNCEMENT, "
                "or let the celebration worker handle CELEBRATION."
            )
        return v


class AnnouncementCreateRequest(BaseModel):
    """
    Broadcast a notification to all active employees or target by department/employee.
    """
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    department_ids: list[UUID] | None = None
    employee_ids: list[UUID] | None = None


# ══════════════════════════════════════════════════════════════
#  Responses
# ══════════════════════════════════════════════════════════════

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_id: UUID
    employee_id: UUID
    title: str
    message: str
    type: NotificationType
    is_read: bool
    email_sent: bool
    created_at: datetime
    read_at: datetime | None = None

    @field_validator("type", mode="before")
    @classmethod
    def coerce_legacy_type(cls, v: Any) -> Any:
        legacy_remap = {"REWARD_REDEEMED", "POINTS_CREDIT", "BONUS", "CREDIT", "REDEMPTION"}
        if isinstance(v, str) and v.upper() in legacy_remap:
            return "SYSTEM"
        return v


class NotificationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notifications: list[NotificationResponse]
    total: int


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created: int
    recipient_count: int
    title: str
    message: str