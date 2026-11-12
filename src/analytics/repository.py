"""
Concrete implementations of IAnalyticsRepository and IAnalyticsDataProvider.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.models import AuditLog, Notification
from src.analytics.schemas import AuditLogCreate, NotificationCreate
from src.common import internal_client as client_svc


class SQLAlchemyAnalyticsRepository:
    """SQLAlchemy 2.0 implementation for Analytics-owned database tables."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_audit_log(self, payload: AuditLogCreate) -> AuditLog:
        log_entry = AuditLog(**payload.model_dump())
        self.db.add(log_entry)
        await self.db.flush()
        await self.db.refresh(log_entry)
        return log_entry

    async def get_audit_logs(
        self, table_name: str, record_id: uuid.UUID, limit: int = 50
    ) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.table_name == table_name, AuditLog.record_id == record_id)
            .order_by(AuditLog.performed_at.desc())
            .limit(limit)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def create_notification(self, payload: NotificationCreate) -> Notification:
        item = Notification(**payload.model_dump())
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def get_employee_notifications(
        self, employee_id: uuid.UUID, unread_only: bool = False
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.employee_id == employee_id)
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        stmt = stmt.order_by(Notification.created_at.desc())
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def mark_notification_read(self, notification_id: uuid.UUID) -> bool:
        stmt = (
            update(Notification)
            .where(Notification.notification_id == notification_id)
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        res = await self.db.execute(stmt)
        return res.rowcount > 0


class HttpAnalyticsDataProvider:
    """HTTP client adapter fetching analytics data from foreign microservices."""

    async def get_recent_reviews(self, employee_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        return await client_svc.get_recent_reviews(employee_id, limit=limit)

    async def get_leaderboard_data(self, limit: int = 10) -> list[dict[str, Any]]:
        return await client_svc.get_leaderboard_data(limit=limit)

    async def get_wallet_stats(self, employee_id: str | None = None) -> dict[str, Any]:
        return await client_svc.get_wallet_stats(employee_id)

    async def get_review_stats(self, employee_id: str | None = None) -> dict[str, Any]:
        return await client_svc.get_review_stats(employee_id)

    async def get_active_users_count(self) -> dict[str, Any]:
        return await client_svc.get_active_users_count()

    async def get_departments_with_members(self) -> list[dict[str, Any]]:
        return await client_svc.get_departments_with_members()

    async def get_wallet_stats_batch(self, employee_ids: list[str]) -> dict[str, dict[str, Any]]:
        return await client_svc.get_wallet_stats_batch(employee_ids)

    async def get_review_stats_batch(self, employee_ids: list[str]) -> dict[str, dict[str, Any]]:
        return await client_svc.get_review_stats_batch(employee_ids)

    async def get_participation_overview(self) -> dict[str, Any]:
        return await client_svc.get_participation_overview()

    async def get_recognition_trend(self, range_: str) -> dict[str, Any]:
        return await client_svc.get_recognition_trend(range_)

    async def get_recognition_by_user(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]:
        return await client_svc.get_recognition_by_user(range_, page, limit)

    async def get_recognition_by_team(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]:
        return await client_svc.get_recognition_by_team(range_, page, limit)