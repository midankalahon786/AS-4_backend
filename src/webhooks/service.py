"""
src/webhooks/service.py
───────────────────────
Webhook service handling HRIS push events.
Decoupled via IWebhookRepository and PostgreSQL AsyncSession.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from uuid import UUID
from typing import Any

from fastapi import HTTPException, Request, status

from src.common.event_publisher import publish
from src.notifications.cache import (
    dept_key,
    desig_key,
    get_cached_lookup,
    invalidate_employee,
    set_cached_lookup,
    status_key,
)
from src.webhooks.interfaces import IWebhookRepository
from src.webhooks.schemas import (
    HrisEmployeeCreatedPayload,
    HrisEmployeeStatusPayload,
    HrisEmployeeUpdatedPayload,
    HrisWebhookEvent,
)

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
_IDEMPOTENCY_TTL = 86_400  # 24 hours


def verify_signature(body: bytes, x_webhook_signature: str) -> None:
    """Raises HTTP 401 if the HMAC-SHA256 signature does not match[cite: 32]."""
    if not WEBHOOK_SECRET:
        logger.warning("WEBHOOK_SECRET not set — skipping signature check (dev only)[cite: 32]")
        return

    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, x_webhook_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )


async def _is_duplicate(r, event_id: str) -> bool:
    """Returns True if this event_id was already processed in Redis within 24h[cite: 32]."""
    if r is None or not event_id:
        return False
    key = f"webhook:idempotency:{event_id}"
    result = await r.set(key, "1", nx=True, ex=_IDEMPOTENCY_TTL)
    return result is None


class WebhookService:
    def __init__(self, repo: IWebhookRepository) -> None:
        self.repo = repo

    async def handle_hris_event(
        self,
        request: Request,
        event: HrisWebhookEvent,
    ) -> dict[str, Any]:
        r = getattr(request.app.state, "redis", None)

        body = await request.body()
        signature = request.headers.get("x-webhook-signature", "")
        verify_signature(body, signature)

        logger.info("HRIS webhook received: event=%s id=%s", event.event, event.event_id)

        if event.event_id and await _is_duplicate(r, event.event_id):
            logger.info("HRIS webhook: duplicate event_id=%s — skipping", event.event_id)
            return {"received": True, "event": event.event, "skipped": True}

        if event.event == "employee.created":
            await self._handle_employee_created(r, HrisEmployeeCreatedPayload(**event.data))

        elif event.event == "employee.updated":
            await self._handle_employee_updated(r, HrisEmployeeUpdatedPayload(**event.data))

        elif event.event == "employee.status_changed":
            await self._handle_status_changed(r, HrisEmployeeStatusPayload(**event.data))

        else:
            logger.warning("HRIS webhook: unknown event type %r — ignoring", event.event)

        return {"received": True, "event": event.event}

    # ── Lookup Helpers with Redis Cache ───────────────────────────────────────

    async def _get_dept_id(self, r, code: str) -> UUID | None:
        if r:
            cached = await get_cached_lookup(r, dept_key(code))
            if cached and "department_id" in cached:
                return UUID(cached["department_id"])

        dept = await self.repo.get_department_by_code(code)
        if dept and r:
            await set_cached_lookup(
                r,
                dept_key(code),
                {
                    "department_id": str(dept.department_id),
                    "department_code": dept.department_code,
                },
            )
        return dept.department_id if dept else None

    async def _get_desig_id(self, r, code: str) -> UUID | None:
        if r:
            cached = await get_cached_lookup(r, desig_key(code))
            if cached and "designation_id" in cached:
                return UUID(cached["designation_id"])

        desig = await self.repo.get_designation_by_code(code)
        if desig and r:
            await set_cached_lookup(
                r,
                desig_key(code),
                {
                    "designation_id": str(desig.designation_id),
                    "designation_code": desig.designation_code,
                },
            )
        return desig.designation_id if desig else None

    async def _get_status_id(self, r, code: str) -> UUID | None:
        if r:
            cached = await get_cached_lookup(r, status_key(code))
            if cached and "status_id" in cached:
                return UUID(cached["status_id"])

        status_row = await self.repo.get_status_by_code(code, entity_type="GENERAL")
        if status_row and r:
            await set_cached_lookup(
                r,
                status_key(code),
                {
                    "status_id": str(status_row.status_id),
                    "status_code": status_row.status_code,
                },
            )
        return status_row.status_id if status_row else None

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _handle_employee_created(
        self, r, payload: HrisEmployeeCreatedPayload
    ) -> None:
        existing = await self.repo.get_employee_by_email(str(payload.email))
        if existing:
            logger.info("HRIS webhook: employee %s already exists — skipping", payload.email)
            return

        dept_id = await self._get_dept_id(r, payload.department_code)
        if not dept_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown department_code: {payload.department_code}",
            )

        desig_id = await self._get_desig_id(r, payload.designation_code)
        if not desig_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown designation_code: {payload.designation_code}",
            )

        status_id = await self._get_status_id(r, "ACTIVE")
        if not status_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="ACTIVE status not found in status_master.",
            )

        manager_id: UUID | None = None
        if payload.manager_email:
            mgr = await self.repo.get_employee_by_email(str(payload.manager_email))
            if mgr:
                manager_id = mgr.employee_id
            else:
                logger.warning(
                    "HRIS webhook: manager %s not found — manager_id will be null",
                    payload.manager_email,
                )

        new_emp = await self.repo.create_employee_from_hris(
            username=payload.username,
            email=str(payload.email),
            department_id=dept_id,
            designation_id=desig_id,
            status_id=status_id,
            date_of_joining=payload.date_of_joining,
            date_of_birth=payload.date_of_birth,
            manager_id=manager_id,
        )

        # Publish event so Wallet Service provisions the wallet automatically
        await publish(
            "events:employee.created",
            {
                "employee_id": str(new_emp.employee_id),
                "created_by": "hris_webhook",
            },
        )
        logger.info("HRIS webhook: employee created and event published — %s", payload.email)

    async def _handle_employee_updated(
        self, r, payload: HrisEmployeeUpdatedPayload
    ) -> None:
        emp = await self.repo.get_employee_by_email(str(payload.email))
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee not found: {payload.email}",
            )

        patch: dict[str, Any] = {}

        if payload.department_code:
            dept_id = await self._get_dept_id(r, payload.department_code)
            if not dept_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown department_code: {payload.department_code}",
                )
            patch["department_id"] = dept_id

        if payload.designation_code:
            desig_id = await self._get_desig_id(r, payload.designation_code)
            if not desig_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown designation_code: {payload.designation_code}",
                )
            patch["designation_id"] = desig_id

        if payload.manager_email:
            mgr = await self.repo.get_employee_by_email(str(payload.manager_email))
            if mgr:
                patch["manager_id"] = mgr.employee_id

        if payload.date_of_birth:
            patch["date_of_birth"] = datetime.fromisoformat(payload.date_of_birth)

        if patch:
            await self.repo.update_employee_from_hris(emp.employee_id, patch)

        if r:
            await invalidate_employee(r, str(emp.employee_id))

        logger.info("HRIS webhook: employee updated — %s", payload.email)

    async def _handle_status_changed(
        self, r, payload: HrisEmployeeStatusPayload
    ) -> None:
        emp = await self.repo.get_employee_by_email(str(payload.email))
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee not found: {payload.email}",
            )

        status_id = await self._get_status_id(r, payload.status_code)
        if not status_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown status_code: {payload.status_code}",
            )

        await self.repo.update_employee_from_hris(emp.employee_id, {"status_id": status_id})

        if r:
            await invalidate_employee(r, str(emp.employee_id))

        logger.info("HRIS webhook: status changed — %s -> %s", payload.email, payload.status_code)