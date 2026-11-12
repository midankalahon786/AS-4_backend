"""
Abstract interfaces / protocols for the Analytics domain.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol
from src.analytics.models import AuditLog, Notification
from src.analytics.schemas import (
    AuditLogCreate,
    NotificationCreate,
)


class IAnalyticsRepository(Protocol):
    """Data access contract for tables owned by Analytics (audit_log, notifications)."""

    async def create_audit_log(self, payload: AuditLogCreate) -> AuditLog:
        ...

    async def get_audit_logs(
        self, table_name: str, record_id: uuid.UUID, limit: int = 50
    ) -> list[AuditLog]:
        ...

    async def create_notification(self, payload: NotificationCreate) -> Notification:
        ...

    async def get_employee_notifications(
        self, employee_id: uuid.UUID, unread_only: bool = False
    ) -> list[Notification]:
        ...

    async def mark_notification_read(self, notification_id: uuid.UUID) -> bool:
        ...


class IAnalyticsDataProvider(Protocol):
    """External client contract for aggregating stats from foreign microservices."""

    async def get_recent_reviews(self, employee_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        ...

    async def get_leaderboard_data(self, limit: int = 10) -> list[dict[str, Any]]:
        ...

    async def get_wallet_stats(self, employee_id: str | None = None) -> dict[str, Any]:
        ...

    async def get_review_stats(self, employee_id: str | None = None) -> dict[str, Any]:
        ...

    async def get_active_users_count(self) -> dict[str, Any]:
        ...

    async def get_departments_with_members(self) -> list[dict[str, Any]]:
        ...

    async def get_wallet_stats_batch(self, employee_ids: list[str]) -> dict[str, dict[str, Any]]:
        ...

    async def get_review_stats_batch(self, employee_ids: list[str]) -> dict[str, dict[str, Any]]:
        ...

    async def get_participation_overview(self) -> dict[str, Any]:
        ...

    async def get_recognition_trend(self, range_: str) -> dict[str, Any]:
        ...

    async def get_recognition_by_user(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]:
        ...

    async def get_recognition_by_team(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]:
        ...