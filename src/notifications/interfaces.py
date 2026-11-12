"""
src/notifications/interfaces.py
───────────────────────────────
Abstract repository contract for notification ledgering, celebration sentinels,
and worker queue operations.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from src.notifications.models import Notification


class INotificationRepository(Protocol):
    # ── Notification Mutations ───────────────────────────────────────
    async def create_notification(
        self,
        employee_id: uuid.UUID,
        title: str,
        message: str,
        notification_type: str,
    ) -> Notification: ...

    async def create_bulk_notifications(
        self,
        employee_ids: list[uuid.UUID],
        title: str,
        message: str,
        notification_type: str,
    ) -> list[Notification]: ...

    # ── Notification Queries & Reads ─────────────────────────────────
    async def get_notifications(
        self,
        employee_id: uuid.UUID,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[Notification]: ...

    async def get_unread_count(self, employee_id: uuid.UUID) -> int: ...

    async def mark_as_read(
        self,
        notification_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> Notification | None: ...

    async def mark_all_as_read(self, employee_id: uuid.UUID) -> int: ...

    # ── Worker & Delivery Ledger Operations ──────────────────────────
    async def get_notification_by_id(
        self, notification_id: uuid.UUID
    ) -> Notification | None: ...

    async def mark_email_sent(self, notification_id: uuid.UUID) -> None: ...

    async def mark_email_unsent(self, notification_id: uuid.UUID) -> None: ...

    async def get_pending_recovery_notifications(
        self, cutoff: datetime, max_attempts: int
    ) -> list[Notification]: ...

    # ── Employee Lookups ─────────────────────────────────────────────
    async def get_all_active_employee_ids(self) -> list[uuid.UUID]: ...

    async def get_active_employee_ids_by_departments(
        self, department_ids: list[uuid.UUID]
    ) -> list[uuid.UUID]: ...

    async def get_active_employee_records(self) -> list[dict[str, Any]]: ...

    async def get_employee_minimal(
        self, employee_id: uuid.UUID
    ) -> dict[str, Any] | None: ...

    # ── Celebrations & Sentinels ─────────────────────────────────────
    async def get_employees_with_celebrations_today(self) -> list[dict[str, Any]]: ...

    async def celebration_already_sent_today(
        self, employee_id: uuid.UUID, celebration_type: str
    ) -> bool: ...

    async def create_sentinel(
        self,
        employee_id: uuid.UUID,
        celebration_type: str,
        celebrant_name: str,
    ) -> Notification: ...