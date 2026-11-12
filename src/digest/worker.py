"""
src/digest/worker.py
────────────────────
Weekly digest background worker firing Mondays at 08:00 UTC[cite: 38].
Powered by SQLAlchemy 2.0 async sessions[cite: 38].
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.digest.service import DigestService
from src.employees.models import Employee, StatusMaster
from src.notifications.email_sender import EmailSender
from src.notifications.models import Notification
from src.roles.models import EmployeeRole, Role

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS: int = 60
DIGEST_WEEKDAY: int = 0  # Monday[cite: 38]
DIGEST_HOUR_UTC: int = 8  # 08:00 UTC[cite: 38]

_running: bool = False


async def digest_worker_loop(
    session_factory: async_sessionmaker[AsyncSession],
    email_sender: EmailSender,
) -> None:
    logger.info("Digest worker started — fires Mondays at %02d:00 UTC", DIGEST_HOUR_UTC)

    while True:
        try:
            now = datetime.now(tz=timezone.utc)
            if now.weekday() == DIGEST_WEEKDAY and now.hour == DIGEST_HOUR_UTC:
                await _run_digest(session_factory, email_sender)
        except asyncio.CancelledError:
            logger.info("Digest worker shutting down.")
            raise
        except Exception:
            logger.exception("Digest worker: unexpected error")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _already_sent_today(session: AsyncSession) -> bool:
    start_of_day = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    stmt = (
        select(Notification.notification_id)
        .where(
            Notification.type == "SYSTEM",
            Notification.title.like("[DIGEST]%"),
            Notification.created_at >= start_of_day,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _write_sentinel(session: AsyncSession) -> None:
    # Pick any employee ID to satisfy foreign key requirement on notification
    emp_stmt = select(Employee.employee_id).limit(1)
    employee_id = (await session.execute(emp_stmt)).scalar_one_or_none()
    if not employee_id:
        raise RuntimeError("Digest worker: no employees found in database")

    now = datetime.now(tz=timezone.utc)
    sentinel = Notification(
        employee_id=employee_id,
        title=f"[DIGEST] Weekly digest sentinel {date.today().isoformat()}",
        message="Automated digest worker sentinel — do not display.",
        type="SYSTEM",
        is_read=True,
        email_sent=True,
        created_at=now,
    )
    session.add(sentinel)
    await session.commit()


async def _get_managers(session: AsyncSession) -> list[tuple[str, UUID]]:
    """Return (email, employee_id) for all active managers[cite: 38]."""
    stmt = (
        select(Employee.email, Employee.employee_id)
        .join(StatusMaster, Employee.status_id == StatusMaster.status_id)
        .join(EmployeeRole, Employee.employee_id == EmployeeRole.employee_id)
        .join(Role, EmployeeRole.role_id == Role.role_id)
        .where(
            StatusMaster.status_code.in_(("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")),
            EmployeeRole.is_active.is_(True),
            func.upper(Role.role_code).contains("MANAGER"),
        )
        .distinct()
    )
    return list((await session.execute(stmt)).all())


async def _run_digest(
    session_factory: async_sessionmaker[AsyncSession],
    email_sender: EmailSender,
) -> None:
    global _running

    if _running:
        logger.debug("Digest worker: run already in progress — skipping tick.")
        return

    async with session_factory() as session:
        if await _already_sent_today(session):
            logger.info("Digest worker: sentinel found — skipping duplicate run.")
            return

        _running = True
        try:
            await _write_sentinel(session)
            managers = await _get_managers(session)
            if not managers:
                logger.warning("Digest worker: no manager accounts found.")
                return
        finally:
            _running = False

    # Dispatch digests to each manager
    async def _send_one(email: str, manager_id: UUID) -> None:
        async with session_factory() as manager_session:
            svc = DigestService(manager_session, email_sender)
            result = await svc.send_digest_email(
                manager_email=email,
                manager_id=manager_id,
            )
            if not result.success:
                logger.warning("Digest worker: failed to send digest to %s", email)

    await asyncio.gather(*[_send_one(email, mid) for email, mid in managers])
    logger.info("Digest worker: digest successfully dispatched to %d manager(s).", len(managers))