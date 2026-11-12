"""
src/webhooks/schemas.py
───────────────────────
Pydantic v2 schemas for HRIS push webhook events and payloads.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class HrisEmployeeCreatedPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    external_id: str
    username: str
    email: EmailStr
    department_code: str
    designation_code: str
    date_of_joining: str
    date_of_birth: str | None = None
    manager_email: EmailStr | None = None


class HrisEmployeeUpdatedPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr
    department_code: str | None = None
    designation_code: str | None = None
    manager_email: EmailStr | None = None
    date_of_birth: str | None = None


class HrisEmployeeStatusPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr
    status_code: str


class HrisWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str | None = Field(default=None, description="Idempotency key sent by HRIS")
    event: str
    data: dict[str, Any]


class WebhookResponse(BaseModel):
    received: bool
    event: str
    skipped: bool = False