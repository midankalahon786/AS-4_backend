"""
src/notifications/service.py
────────────────────────────
Notification service decoupled via INotificationRepository.
Pushes notification IDs to the Redis queue for worker pickup[cite: 44].
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from src.notifications import schemas
from src.notifications.interfaces import INotificationRepository

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, repo: INotificationRepository | AsyncSession, redis=None) -> None:
        if isinstance(repo, AsyncSession):
            from src.notifications.repository import SQLAlchemyNotificationRepository
            self.repo = SQLAlchemyNotificationRepository(repo)
        else:
            self.repo = repo
        self._redis = redis

    # ── Core Creation ─────────────────────────────────────────────────────────

    async def create_notification(
        self,
        *,
        employee_id: UUID | str,
        title: str,
        message: str,
        type: schemas.NotificationType,
    ) -> dict[str, Any]:
        emp_id = UUID(str(employee_id))
        record = await self.repo.create_notification(
            employee_id=emp_id,
            title=title,
            message=message,
            notification_type=type.value,
        )
        logger.debug(
            "Notification created: id=%s employee=%s type=%s",
            record.notification_id,
            emp_id,
            type,
        )

        if self._redis is not None:
            from src.notifications.cache import enqueue_notification
            await enqueue_notification(self._redis, str(record.notification_id))

        return {
            "notification_id": record.notification_id,
            "employee_id": record.employee_id,
            "title": record.title,
            "message": record.message,
            "type": record.type,
            "is_read": record.is_read,
            "email_sent": record.email_sent,
            "created_at": record.created_at,
            "read_at": record.read_at,
        }

    # ── Bulk Helpers ──────────────────────────────────────────────────────────

    async def create_bulk_notifications(
        self,
        *,
        employee_ids: list[UUID | str],
        title: str,
        message: str,
        type: schemas.NotificationType,
    ) -> list[dict[str, Any]]:
        parsed_ids = [UUID(str(eid)) for eid in employee_ids]
        records = await self.repo.create_bulk_notifications(
            employee_ids=parsed_ids,
            title=title,
            message=message,
            notification_type=type.value,
        )

        if self._redis is not None:
            from src.notifications.cache import enqueue_notification
            for rec in records:
                await enqueue_notification(self._redis, str(rec.notification_id))

        logger.info(
            "Bulk notifications created: count=%d type=%s title=%r",
            len(records),
            type,
            title,
        )
        return [
            {
                "notification_id": r.notification_id,
                "employee_id": r.employee_id,
                "title": r.title,
                "message": r.message,
                "type": r.type,
                "is_read": r.is_read,
                "email_sent": r.email_sent,
                "created_at": r.created_at,
                "read_at": r.read_at,
            }
            for r in records
        ]

    async def get_all_active_employee_ids(self) -> list[str]:
        ids = await self.repo.get_all_active_employee_ids()
        return [str(eid) for eid in ids]

    async def get_active_employee_ids_by_department(
        self, department_ids: list[UUID | str]
    ) -> list[str]:
        parsed = [UUID(str(d)) for d in department_ids]
        ids = await self.repo.get_active_employee_ids_by_departments(parsed)
        return [str(eid) for eid in ids]

    # ── Reads & State Updates ─────────────────────────────────────────────────

    async def get_notifications(
        self,
        *,
        employee_id: UUID | str,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[schemas.NotificationResponse]:
        emp_id = UUID(str(employee_id))
        records = await self.repo.get_notifications(
            employee_id=emp_id,
            limit=limit,
            unread_only=unread_only,
        )
        return [schemas.NotificationResponse.model_validate(r) for r in records]

    async def get_unread_count(self, *, employee_id: UUID | str) -> int:
        emp_id = UUID(str(employee_id))
        return await self.repo.get_unread_count(emp_id)

    async def mark_as_read(
        self,
        *,
        notification_id: UUID | str,
        employee_id: UUID | str,
    ) -> schemas.NotificationResponse | None:
        notif_id = UUID(str(notification_id))
        emp_id = UUID(str(employee_id))
        record = await self.repo.mark_as_read(notif_id, emp_id)
        return schemas.NotificationResponse.model_validate(record) if record else None

    async def mark_all_as_read(self, *, employee_id: UUID | str) -> int:
        emp_id = UUID(str(employee_id))
        return await self.repo.mark_all_as_read(emp_id)

    # ── Celebration Helpers ───────────────────────────────────────────────────

    async def get_employees_with_celebrations_today(self) -> list[dict[str, Any]]:
        return await self.repo.get_employees_with_celebrations_today()

    async def celebration_already_sent_today(
        self,
        *,
        employee_id: UUID | str,
        celebration_type: str,
    ) -> bool:
        emp_id = UUID(str(employee_id))
        return await self.repo.celebration_already_sent_today(emp_id, celebration_type)

    async def create_sentinel(
        self,
        *,
        employee_id: UUID | str,
        celebration_type: str,
        celebrant_name: str,
    ) -> dict[str, Any]:
        emp_id = UUID(str(employee_id))
        record = await self.repo.create_sentinel(
            employee_id=emp_id,
            celebration_type=celebration_type,
            celebrant_name=celebrant_name,
        )
        return {
            "notification_id": record.notification_id,
            "employee_id": record.employee_id,
            "title": record.title,
            "message": record.message,
            "type": record.type,
            "is_read": record.is_read,
            "email_sent": record.email_sent,
            "created_at": record.created_at,
        }