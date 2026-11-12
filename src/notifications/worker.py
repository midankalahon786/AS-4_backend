"""
src/notifications/worker.py
───────────────────────────
Background Email + Slack Worker.
Operates on SQLAlchemy 2.0 async sessionmaker with Redis BLPOP queueing[cite: 46].
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from src.notifications.email_sender import EmailSender
    from src.notifications.slack_sender import SlackSender

import redis.asyncio as aioredis

from src.notifications.cache import (
    QUEUE_KEY,
    dequeue_notification,
    get_cached_celebration_employees,
    get_cached_employee,
    get_cached_slack_uid,
    set_cached_celebration_employees,
    set_cached_employee,
    set_cached_slack_uid,
)
from src.notifications.repository import SQLAlchemyNotificationRepository

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_CLAIM_TTL_SECONDS = 600  # 10 minutes[cite: 46]
_RECOVERY_GRACE_SECONDS = 300  # 5 minutes[cite: 46]
_MAX_SEND_ATTEMPTS = 3
_RECOVERY_DONE_KEY = "notify:recovery_done"
EMAILS_PER_SECOND = 10


# ── Claim Lock ────────────────────────────────────────────────────────────────

async def _try_claim(r: aioredis.Redis, notification_id: str) -> bool:
    """Atomically claim notification via SET NX EX[cite: 46]."""
    key = f"processing:{notification_id}"
    try:
        result = await r.set(key, "1", nx=True, ex=_CLAIM_TTL_SECONDS)
        return result is True
    except Exception as exc:
        logger.warning("_try_claim(%s) Redis error — proceeding without lock: %s", notification_id, exc)
        return True


# ── Startup Recovery ──────────────────────────────────────────────────────────

async def _recover_pending(
    session_factory: async_sessionmaker[AsyncSession], r: aioredis.Redis
) -> int:
    with tracer.start_as_current_span("worker_startup_recovery") as span:
        try:
            already_done = await r.exists(_RECOVERY_DONE_KEY)
        except Exception:
            already_done = False

        if already_done:
            logger.info("Worker recovery: notify:recovery_done key present — skipping recovery.")
            span.set_attribute("recovery.skipped", True)
            return 0

        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=_RECOVERY_GRACE_SECONDS)

        async with session_factory() as session:
            repo = SQLAlchemyNotificationRepository(session)
            pending = await repo.get_pending_recovery_notifications(cutoff, _MAX_SEND_ATTEMPTS)

        span.set_attribute("recovery.pending_count", len(pending))

        if pending:
            pipe = r.pipeline()
            for n in pending:
                pipe.lpush(QUEUE_KEY, str(n.notification_id))
            await pipe.execute()
            logger.info(
                "Worker recovery: re-queued %d pending notification(s)",
                len(pending),
            )

        try:
            await r.set(_RECOVERY_DONE_KEY, "1", ex=86400)
        except Exception as exc:
            logger.warning("Worker recovery: failed to set recovery_done key — %s", exc)

        return len(pending)


# ── Employee / Slack UID Helpers ──────────────────────────────────────────────

async def _get_employee(
    session: AsyncSession, r: aioredis.Redis, employee_id: str
) -> dict | None:
    cached = await get_cached_employee(r, employee_id)
    if cached:
        return cached

    repo = SQLAlchemyNotificationRepository(session)
    emp_dict = await repo.get_employee_minimal(UUID(employee_id))
    if emp_dict:
        await set_cached_employee(r, employee_id, emp_dict)
    return emp_dict


async def _get_slack_uid(
    slack: SlackSender | None,
    r: aioredis.Redis,
    email: str,
) -> str | None:
    if not slack:
        return None

    cached = await get_cached_slack_uid(r, email)
    if cached is not None:
        return cached if cached else None

    uid = await slack.get_user_id_by_email(email)
    await set_cached_slack_uid(r, email, uid)
    return uid


# ── Core Processor ────────────────────────────────────────────────────────────

async def _process_one(
    session_factory: async_sessionmaker[AsyncSession],
    sender: EmailSender,
    slack: SlackSender | None,
    r: aioredis.Redis,
    notification_id_str: str,
) -> bool:
    from src.notifications.email_sender import build_notification_html

    with tracer.start_as_current_span("process_single_notification") as span:
        span.set_attribute("notification.id", notification_id_str)

        # 1. Claim lock[cite: 46]
        claimed = await _try_claim(r, notification_id_str)
        if not claimed:
            span.set_attribute("notification.status", "skipped_claim_lost")
            return True

        notif_uuid = UUID(notification_id_str)

        async with session_factory() as session:
            repo = SQLAlchemyNotificationRepository(session)
            notification = await repo.get_notification_by_id(notif_uuid)

            if notification is None:
                span.set_attribute("notification.status", "not_found_in_db")
                return False

            if notification.email_sent:
                span.set_attribute("notification.status", "already_sent")
                return True

            if notification.type == "CELEBRATION":
                span.set_attribute("notification.status", "skipped_celebration_type")
                await repo.mark_email_sent(notif_uuid)
                await session.commit()
                return True

            attempts = notification.send_attempts or 0
            if attempts >= _MAX_SEND_ATTEMPTS:
                span.set_attribute("notification.status", "abandoned_max_attempts")
                logger.error("Notification %s exceeded max attempts (%d)", notif_uuid, attempts)
                return False

            emp_str = str(notification.employee_id)
            employee = await _get_employee(session, r, emp_str)
            if employee is None:
                span.set_attribute("notification.status", "employee_not_found")
                await repo.mark_email_sent(notif_uuid)
                await session.commit()
                return False

            # At-most-once delivery: Claim the row before sending[cite: 46]
            await repo.mark_email_sent(notif_uuid)
            await session.commit()

        # Send email + Slack outside the DB transaction
        try:
            html = build_notification_html(
                title=notification.title,
                message=notification.message,
                type_=notification.type,
            )

            async def _email_coro() -> None:
                with tracer.start_as_current_span("send_smtp_email"):
                    await sender.send_notification_email(
                        to_email=employee["email"],
                        subject=notification.title,
                        body_html=html,
                        type_=notification.type,
                        employee_id=emp_str,
                    )

            async def _slack_coro() -> None:
                try:
                    uid = await _get_slack_uid(slack, r, employee["email"])
                    if uid:
                        with tracer.start_as_current_span("send_slack_dm"):
                            await slack.send_dm(
                                slack_user_id=uid,
                                title=notification.title,
                                message=notification.message,
                                type_=notification.type,
                            )
                except Exception:
                    logger.warning("Slack DM failed for notification %s", notification_id_str)

            await asyncio.gather(_email_coro(), _slack_coro())
            span.set_attribute("notification.status", "success")
            return True

        except Exception as e:
            span.record_exception(e)
            span.set_attribute("notification.status", "failed")
            logger.exception("Failed to send notification %s — reverting flag", notification_id_str)
            async with session_factory() as revert_session:
                revert_repo = SQLAlchemyNotificationRepository(revert_session)
                await revert_repo.mark_email_unsent(notif_uuid)
                await revert_session.commit()
            return False


# ── Worker Loops ──────────────────────────────────────────────────────────────

async def email_worker_loop(
    session_factory: async_sessionmaker[AsyncSession],
    sender: EmailSender,
    r: aioredis.Redis,
    slack: SlackSender | None = None,
) -> None:
    recovered = await _recover_pending(session_factory, r)
    logger.info("Email worker started — BLPOP mode (recovered=%d, queue=%s)", recovered, QUEUE_KEY)

    while True:
        try:
            notification_id = await dequeue_notification(r, timeout=5)
            if notification_id is None:
                continue

            success = await _process_one(session_factory, sender, slack, r, notification_id)
            if success:
                logger.info("Worker: processed notification %s", notification_id)

        except asyncio.CancelledError:
            logger.info("Email worker shutting down.")
            raise
        except Exception:
            logger.exception("Email worker unexpected error")
            await asyncio.sleep(2)


# ── Celebration Processor (APScheduler Entry) ─────────────────────────────────

async def process_celebrations(
    session_factory: async_sessionmaker[AsyncSession],
    sender: EmailSender,
    r: aioredis.Redis,
    slack: SlackSender | None = None,
) -> None:
    from src.notifications.email_sender import build_celebration_html
    from src.notifications.schemas import NotificationType
    from src.notifications.service import NotificationService

    with tracer.start_as_current_span("check_daily_celebrations") as main_span:
        async with session_factory() as session:
            repo = SQLAlchemyNotificationRepository(session)
            svc = NotificationService(repo=repo, redis=r)
            celebrants = await svc.get_employees_with_celebrations_today()
            main_span.set_attribute("celebrants.count", len(celebrants))

            if not celebrants:
                logger.debug("Celebration worker: no celebrations today.")
                return

            all_active_employees = await _get_all_active_employees_cached(session, r)
            if not all_active_employees:
                logger.warning("Celebration worker: no active employees found.")
                return

            for person in celebrants:
                emp_id = person["employee_id"]
                c_type = person["celebration_type"]
                username = person["username"]

                already_sent = await svc.celebration_already_sent_today(
                    employee_id=emp_id, celebration_type=c_type
                )
                if already_sent:
                    continue

                # Write sentinel FIRST before sending[cite: 46]
                await svc.create_sentinel(
                    employee_id=emp_id,
                    celebration_type=c_type,
                    celebrant_name=username,
                )
                await session.commit()

                personal_subject, personal_html = build_celebration_html(
                    employee_name=username,
                    celebration_type=c_type,
                    years=person.get("years"),
                    is_personal=True,
                )
                broadcast_subject, broadcast_html = build_celebration_html(
                    employee_name=username,
                    celebration_type=c_type,
                    years=person.get("years"),
                    is_personal=False,
                )
                broadcast_plain = (
                    f"[{c_type}] Today is {username}'s birthday! Wish them a great day."
                    if c_type == "BIRTHDAY"
                    else f"[{c_type}] {username} is celebrating their {person.get('years')}-year work anniversary today."
                )

                # Slack Broadcast
                if slack:
                    asyncio.create_task(
                        slack.send_celebration(
                            channel_id=None,
                            employee_name=username,
                            celebration_type=c_type,
                            years=person.get("years"),
                        )
                    )

                # Rate-limited email broadcast[cite: 46]
                for i, recipient in enumerate(all_active_employees):
                    is_celebrant = recipient["employee_id"] == str(emp_id)
                    subject_to_send = personal_subject if is_celebrant else broadcast_subject
                    html_to_send = personal_html if is_celebrant else broadcast_html
                    plain_to_send = (
                        f"[{c_type}] Happy {c_type.replace('_', ' ').title()}, {username}!"
                        if is_celebrant
                        else broadcast_plain
                    )

                    notif = await svc.create_notification(
                        employee_id=recipient["employee_id"],
                        title=subject_to_send,
                        message=plain_to_send,
                        type=NotificationType.CELEBRATION,
                    )
                    await repo.mark_email_sent(notif["notification_id"])
                    await session.commit()

                    try:
                        await sender.send_notification_email(
                            to_email=recipient["email"],
                            subject=subject_to_send,
                            body_html=html_to_send,
                        )
                    except Exception:
                        await repo.mark_email_unsent(notif["notification_id"])
                        await session.commit()

                    if (i + 1) % EMAILS_PER_SECOND == 0:
                        await asyncio.sleep(1)


async def _get_all_active_employees_cached(session: AsyncSession, r: aioredis.Redis) -> list[dict]:
    cached = await get_cached_celebration_employees(r)
    if cached is not None:
        return cached

    repo = SQLAlchemyNotificationRepository(session)
    active = await repo.get_active_employee_records()
    await set_cached_celebration_employees(r, active)
    return active