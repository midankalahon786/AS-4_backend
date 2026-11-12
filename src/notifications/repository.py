"""
src/notifications/repository.py
───────────────────────────────
SQLAlchemy 2.0 implementation of INotificationRepository.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, not_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.employees.models import Employee, StatusMaster
from src.notifications.models import Notification

_LEGACY_TYPES = ["REWARD_REDEEMED", "POINTS_CREDIT", "BONUS", "CREDIT", "REDEMPTION"]


class SQLAlchemyNotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Notification Mutations ───────────────────────────────────────

    async def create_notification(
        self,
        employee_id: uuid.UUID,
        title: str,
        message: str,
        notification_type: str,
    ) -> Notification:
        now = datetime.now(timezone.utc)
        record = Notification(
            employee_id=employee_id,
            title=title,
            message=message,
            type=notification_type,
            is_read=False,
            email_sent=False,
            send_attempts=0,
            created_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def create_bulk_notifications(
        self,
        employee_ids: list[uuid.UUID],
        title: str,
        message: str,
        notification_type: str,
    ) -> list[Notification]:
        now = datetime.now(timezone.utc)
        records = [
            Notification(
                employee_id=eid,
                title=title,
                message=message,
                type=notification_type,
                is_read=False,
                email_sent=False,
                send_attempts=0,
                created_at=now,
            )
            for eid in employee_ids
        ]
        self.db.add_all(records)
        await self.db.flush()
        return records

    # ── Notification Queries & Reads ─────────────────────────────────

    async def get_notifications(
        self,
        employee_id: uuid.UUID,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.employee_id == employee_id,
                not_(Notification.title.like("[SENTINEL]%")),
                not_(Notification.type.in_(_LEGACY_TYPES)),
            )
        )
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))

        ordered_stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
        return list((await self.db.execute(ordered_stmt)).scalars().all())

    async def get_unread_count(self, employee_id: uuid.UUID) -> int:
        stmt = select(func.count(Notification.notification_id)).where(
            Notification.employee_id == employee_id,
            Notification.is_read.is_(False),
            not_(Notification.title.like("[SENTINEL]%")),
            not_(Notification.type.in_(_LEGACY_TYPES)),
        )
        return (await self.db.execute(stmt)).scalar() or 0

    async def mark_as_read(
        self,
        notification_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> Notification | None:
        now = datetime.now(timezone.utc)
        stmt = (
            update(Notification)
            .where(
                Notification.notification_id == notification_id,
                Notification.employee_id == employee_id,
            )
            .values(is_read=True, read_at=now)
            .returning(Notification)
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def mark_all_as_read(self, employee_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        stmt = (
            update(Notification)
            .where(
                Notification.employee_id == employee_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=now)
        )
        res = await self.db.execute(stmt)
        return res.rowcount

    # ── Worker & Delivery Ledger Operations ──────────────────────────

    async def get_notification_by_id(
        self, notification_id: uuid.UUID
    ) -> Notification | None:
        stmt = select(Notification).where(Notification.notification_id == notification_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def mark_email_sent(self, notification_id: uuid.UUID) -> None:
        stmt = (
            update(Notification)
            .where(Notification.notification_id == notification_id)
            .values(email_sent=True)
        )
        await self.db.execute(stmt)

    async def mark_email_unsent(self, notification_id: uuid.UUID) -> None:
        stmt = (
            update(Notification)
            .where(Notification.notification_id == notification_id)
            .values(
                email_sent=False,
                send_attempts=Notification.send_attempts + 1,
            )
        )
        await self.db.execute(stmt)

    async def get_pending_recovery_notifications(
        self, cutoff: datetime, max_attempts: int
    ) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.email_sent.is_(False),
                Notification.type != "CELEBRATION",
                Notification.send_attempts < max_attempts,
                Notification.created_at < cutoff,
            )
            .order_by(Notification.created_at.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # ── Employee Lookups ─────────────────────────────────────────────

    async def get_all_active_employee_ids(self) -> list[uuid.UUID]:
        stmt = (
            select(Employee.employee_id)
            .join(StatusMaster, Employee.status_id == StatusMaster.status_id)
            .where(StatusMaster.status_code.in_(("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")))
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_active_employee_ids_by_departments(
        self, department_ids: list[uuid.UUID]
    ) -> list[uuid.UUID]:
        stmt = (
            select(Employee.employee_id)
            .join(StatusMaster, Employee.status_id == StatusMaster.status_id)
            .where(
                Employee.department_id.in_(department_ids),
                StatusMaster.status_code.in_(("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")),
            )
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_active_employee_records(self) -> list[dict[str, Any]]:
        stmt = (
            select(Employee.employee_id, Employee.email, Employee.username)
            .join(StatusMaster, Employee.status_id == StatusMaster.status_id)
            .where(StatusMaster.status_code.in_(("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")))
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "employee_id": str(r[0]),
                "email": r[1],
                "username": r[2],
            }
            for r in rows
        ]

    async def get_employee_minimal(
        self, employee_id: uuid.UUID
    ) -> dict[str, Any] | None:
        stmt = select(Employee.employee_id, Employee.email, Employee.username).where(
            Employee.employee_id == employee_id
        )
        row = (await self.db.execute(stmt)).first()
        if not row:
            return None
        return {
            "employee_id": str(row[0]),
            "email": row[1],
            "username": row[2],
        }

    # ── Celebrations & Sentinels ─────────────────────────────────────

    async def get_employees_with_celebrations_today(self) -> list[dict[str, Any]]:
        today = date.today()
        month, day = today.month, today.day

        stmt = (
            select(
                Employee.employee_id,
                Employee.username,
                Employee.email,
                Employee.date_of_birth,
                Employee.date_of_joining,
            )
            .join(StatusMaster, Employee.status_id == StatusMaster.status_id)
            .where(StatusMaster.status_code == "ACTIVE")
        )
        rows = (await self.db.execute(stmt)).all()

        celebrants: list[dict[str, Any]] = []
        for emp_id, username, email, dob, doj in rows:
            if dob is not None and dob.month == month and dob.day == day:
                celebrants.append({
                    "employee_id": emp_id,
                    "username": username,
                    "email": email,
                    "celebration_type": "BIRTHDAY",
                    "years": None,
                })

            if doj is not None and doj.month == month and doj.day == day and doj.year != today.year:
                celebrants.append({
                    "employee_id": emp_id,
                    "username": username,
                    "email": email,
                    "celebration_type": "WORK_ANNIVERSARY",
                    "years": today.year - doj.year,
                })

        return celebrants

    async def celebration_already_sent_today(
        self, employee_id: uuid.UUID, celebration_type: str
    ) -> bool:
        start_of_day = datetime.combine(date.today(), datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        stmt = (
            select(Notification.notification_id)
            .where(
                Notification.employee_id == employee_id,
                Notification.type == "CELEBRATION",
                Notification.title.like("[SENTINEL]%"),
                Notification.message.like(f"%[{celebration_type}]%"),
                Notification.created_at >= start_of_day,
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def create_sentinel(
        self,
        employee_id: uuid.UUID,
        celebration_type: str,
        celebrant_name: str,
    ) -> Notification:
        now = datetime.now(timezone.utc)
        record = Notification(
            employee_id=employee_id,
            title=f"[SENTINEL] {celebrant_name}",
            message=f"[{celebration_type}] broadcast initiated",
            type="CELEBRATION",
            is_read=True,
            email_sent=True,
            send_attempts=0,
            created_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        return record