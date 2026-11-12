"""
src/wallet/employee_consumer.py
────────────────────────────────
Redis Stream consumer — listens on 'events:employee.created'
and provisions a wallet for each new employee[cite: 26].
Powered by SQLAlchemy 2.0 Async Session Factory.

Consumer group : wallet-service[cite: 26]
Consumer name  : employee-wallet-worker-1[cite: 26]
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from src.common.audit import audit_ctx
from src.core.database import async_session_factory
from src.wallet.models import Wallet

logger = logging.getLogger(__name__)

STREAM_KEY = "events:employee.created"
GROUP_NAME = "wallet-service"
CONSUMER_NAME = "employee-wallet-worker-1"
BLOCK_MS = 2000
BATCH_SIZE = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _ensure_group(r) -> None:
    try:
        await r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info("Consumer group '%s' created on '%s'", GROUP_NAME, STREAM_KEY)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _provision_wallet(
    employee_id: UUID, created_by: UUID | None, ip_address: str | None = None
) -> None:
    """Create a wallet if one doesn't already exist — idempotent[cite: 26]."""
    async with async_session_factory() as session:
        # 1. Idempotency check
        stmt = select(Wallet).where(Wallet.employee_id == employee_id)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            logger.debug("Wallet already exists for %s", employee_id)
            return

        now = _now()
        new_wallet = Wallet(
            employee_id=employee_id,
            available_points=0,
            redeemed_points=0,
            total_earned_points=0,
            version=1,
            created_by=created_by,
            updated_by=created_by,
            created_at=now,
            updated_at=now,
        )

        async with audit_ctx(
            user_id=str(created_by) if created_by else "system",
            request=None,
            ip_address=ip_address,
            table_name="wallets",
            record_id=lambda: str(new_wallet.wallet_id),
            operation="INSERT",
            new_values=lambda: {
                "employee_id": str(employee_id),
                "available_points": 0,
                "redeemed_points": 0,
                "total_earned_points": 0,
                "created_by": str(created_by) if created_by else "system",
            },
        ):
            session.add(new_wallet)
            await session.commit()

        logger.info("Wallet provisioned for employee %s", employee_id)


async def _handle_message(r, msg_id: str, fields: dict) -> None:
    raw_emp_id = fields.get("employee_id", "")
    raw_created_by = fields.get("created_by")
    ip_address = fields.get("ip_address") or None

    if not raw_emp_id:
        logger.warning("employee.created msg %s missing employee_id", msg_id)
        await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
        return

    try:
        employee_id = UUID(raw_emp_id)
        created_by = UUID(raw_created_by) if raw_created_by and raw_created_by != "system" else None
        await _provision_wallet(employee_id, created_by, ip_address)
        await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
    except Exception as exc:
        logger.error("Failed to provision wallet for %s: %s", raw_emp_id, exc)


async def _recover_pending(r) -> None:
    try:
        pending = await r.xpending_range(
            STREAM_KEY, GROUP_NAME, min="-", max="+", count=100
        )
        if not pending:
            return
        logger.info("Recovering %d pending employee.created messages", len(pending))
        for entry in pending:
            msg_id = entry["message_id"]
            msgs = await r.xrange(STREAM_KEY, min=msg_id, max=msg_id)
            if msgs:
                _, fields = msgs[0]
                await _handle_message(r, msg_id, fields)
    except Exception as exc:
        logger.warning("employee.created pending recovery failed: %s", exc)


async def employee_created_consumer_loop(shutdown_event: asyncio.Event) -> None:
    from src.notifications.redis_client import get_redis

    try:
        r = get_redis()
    except RuntimeError:
        logger.warning("Redis unavailable — employee.created consumer disabled")
        return

    await _ensure_group(r)
    await _recover_pending(r)
    logger.info("employee.created consumer started")

    while not shutdown_event.is_set():
        try:
            results = await r.xreadgroup(
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: ">"},
                count=BATCH_SIZE,
                block=BLOCK_MS,
            )
            if not results:
                await asyncio.sleep(0.5)
                continue
            for _stream, messages in results:
                for msg_id, fields in messages:
                    await _handle_message(r, msg_id, fields)
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("employee.created consumer error: %s", exc)
            if "NOGROUP" in str(exc):
                try:
                    await _ensure_group(r)
                except Exception as eg_exc:
                    logger.error("employee.created _ensure_group recovery failed: %s", eg_exc)
            await asyncio.sleep(2)

    logger.info("employee.created consumer stopped")