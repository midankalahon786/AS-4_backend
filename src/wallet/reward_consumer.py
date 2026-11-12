"""
src/wallet/reward_consumer.py
──────────────────────────────
Redis Stream consumer — listens on 'events:reward.redeemed'
and deducts points from the wallet's available_points[cite: 28].
Powered by SQLAlchemy 2.0 Async Session Factory.

Idempotency: Checks for an existing DEBIT transaction with
reference_number = f"redemption:{history_id}" before writing[cite: 28].

Consumer group : wallet-service[cite: 28]
Consumer name  : reward-debit-worker-1[cite: 28]
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update

from src.common.audit import audit_ctx
from src.common.cache import cache_delete
from src.core.database import async_session_factory
from src.employees.models import StatusMaster
from src.notifications.schemas import NotificationType
from src.notifications.service import NotificationService
from src.wallet.models import PointTransaction, TransactionType, Wallet

logger = logging.getLogger(__name__)

STREAM_KEY = "events:reward.redeemed"
GROUP_NAME = "wallet-service"
CONSUMER_NAME = "reward-debit-worker-1"
BLOCK_MS = 2000
BATCH_SIZE = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _ensure_group(r) -> None:
    try:
        await r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _deduct_points(
    history_id: UUID,
    wallet_id: UUID,
    points: int,
    redeemed_by: UUID | None,
    ip_address: str | None = None,
) -> None:
    """Deduct points from wallet idempotently via reference_number[cite: 28]."""
    ref_number = f"redemption:{history_id}"

    async with async_session_factory() as session:
        # 1. Idempotency Check
        existing_txn = (
            await session.execute(
                select(PointTransaction.transaction_id).where(
                    PointTransaction.reference_number == ref_number
                )
            )
        ).scalar_one_or_none()
        if existing_txn:
            logger.debug("Deduction for redemption %s already recorded — skipping", history_id)
            return

        # 2. Fetch Wallet
        wallet = (
            await session.execute(select(Wallet).where(Wallet.wallet_id == wallet_id))
        ).scalar_one_or_none()
        if not wallet:
            raise RuntimeError(f"Wallet {wallet_id} not found")

        deduct_amount = min(points, wallet.available_points)

        # 3. Resolve DEBIT type and SUCCESS status
        debit_type_stmt = select(TransactionType).where(
            TransactionType.is_credit.is_(False),
            TransactionType.type_code == "REWARD_REDEMPTION",
        )
        debit_type = (await session.execute(debit_type_stmt)).scalar_one_or_none()
        if not debit_type:
            fallback_debit = select(TransactionType).where(TransactionType.is_credit.is_(False))
            debit_type = (await session.execute(fallback_debit)).scalar_one_or_none()

        status_stmt = select(StatusMaster).where(
            StatusMaster.status_code == "SUCCESS",
            StatusMaster.entity_type == "TRANSACTION",
        )
        status_rec = (await session.execute(status_stmt)).scalar_one_or_none()
        if not status_rec:
            fallback_status = select(StatusMaster).where(StatusMaster.status_code == "SUCCESS")
            status_rec = (await session.execute(fallback_status)).scalar_one_or_none()

        if not debit_type or not status_rec:
            raise RuntimeError("Missing debit transaction_type or SUCCESS status in DB")

        wallet_before = {
            "available_points": wallet.available_points,
            "redeemed_points": wallet.redeemed_points,
        }

        now = _now()
        new_txn = PointTransaction(
            wallet_id=wallet_id,
            amount=deduct_amount,
            transaction_type_id=debit_type.type_id,
            status_id=status_rec.status_id,
            reference_number=ref_number,
            description=f"Points deducted for reward redemption {history_id}",
            transaction_at=now,
            created_by=redeemed_by,
            updated_by=redeemed_by,
            created_at=now,
            updated_at=now,
        )

        async with audit_ctx(
            user_id=str(redeemed_by) if redeemed_by else "system",
            request=None,
            ip_address=ip_address,
            table_name="transactions",
            record_id=lambda: str(new_txn.transaction_id),
            operation="REDEEM",
            old_values=wallet_before,
            new_values=lambda: {
                "available_points": wallet_before["available_points"] - deduct_amount,
                "redeemed_points": wallet_before["redeemed_points"] + deduct_amount,
                "points_deducted": deduct_amount,
                "history_id": str(history_id),
                "reference": ref_number,
            },
        ):
            session.add(new_txn)

            update_wallet_stmt = (
                update(Wallet)
                .where(Wallet.wallet_id == wallet_id, Wallet.version == wallet.version)
                .values(
                    available_points=Wallet.available_points - deduct_amount,
                    redeemed_points=Wallet.redeemed_points + deduct_amount,
                    version=Wallet.version + 1,
                    updated_by=redeemed_by,
                    updated_at=now,
                )
            )
            update_res = await session.execute(update_wallet_stmt)
            if update_res.rowcount == 0:
                raise RuntimeError("Concurrent wallet update detected during reward redemption debit")

            await session.commit()

        # Invalidate Cache
        await cache_delete(f"wallets:employee:{wallet.employee_id}")
        logger.info("Deducted %d points from wallet %s for redemption %s", deduct_amount, wallet_id, history_id)

        # 4. Notifications
        try:
            from src.notifications.redis_client import get_redis
            try:
                r = get_redis()
            except RuntimeError:
                r = None

            notif_svc = NotificationService(session, redis=r)
            await notif_svc.create_notification(
                employee_id=wallet.employee_id,
                title=f"Reward Redeemed — {deduct_amount} points deducted",
                message=(
                    f"{deduct_amount} points have been deducted from your wallet "
                    f"for reward redemption (Ref: {history_id})."
                ),
                type=NotificationType.REWARD,
            )
        except Exception:
            logger.warning("REWARD notification failed for wallet %s — points still deducted", wallet_id)


async def _handle_message(r, msg_id: str, fields: dict) -> None:
    raw_history_id = fields.get("history_id", "")
    raw_wallet_id = fields.get("wallet_id", "")
    raw_redeemed_by = fields.get("redeemed_by")
    ip_address = fields.get("ip_address") or None
    try:
        points = int(fields.get("points", "0"))
    except ValueError:
        points = 0

    if not raw_history_id or not raw_wallet_id:
        await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
        return

    try:
        history_id = UUID(raw_history_id)
        wallet_id = UUID(raw_wallet_id)
        redeemed_by = UUID(raw_redeemed_by) if raw_redeemed_by and raw_redeemed_by != "system" else None

        await _deduct_points(history_id, wallet_id, points, redeemed_by, ip_address)
        await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
    except RuntimeError as exc:
        err = str(exc).lower()
        if "not found" in err or "missing" in err:
            logger.error("Dead-letter: unrecoverable error for redemption %s: %s — ACKing", raw_history_id, exc)
            await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
        else:
            logger.error("Transient error deducting points for redemption %s: %s", raw_history_id, exc)
    except Exception as exc:
        logger.error("Failed to deduct points for redemption %s: %s", raw_history_id, exc)


async def _recover_pending(r) -> None:
    try:
        pending = await r.xpending_range(STREAM_KEY, GROUP_NAME, min="-", max="+", count=100)
        if not pending:
            return
        for entry in pending:
            msg_id = entry["message_id"]
            msgs = await r.xrange(STREAM_KEY, min=msg_id, max=msg_id)
            if msgs:
                _, fields = msgs[0]
                await _handle_message(r, msg_id, fields)
    except Exception as exc:
        logger.warning("reward.redeemed recovery failed: %s", exc)


async def reward_redeemed_consumer_loop(shutdown_event: asyncio.Event) -> None:
    from src.notifications.redis_client import get_redis

    try:
        r = get_redis()
    except RuntimeError:
        logger.warning("Redis unavailable — reward.redeemed consumer disabled")
        return

    await _ensure_group(r)
    await _recover_pending(r)
    logger.info("reward.redeemed consumer started ✅")

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
            logger.error("reward.redeemed consumer error: %s", exc)
            if "NOGROUP" in str(exc):
                try:
                    await _ensure_group(r)
                except Exception as eg_exc:
                    logger.error("reward.redeemed _ensure_group recovery failed: %s", eg_exc)
            await asyncio.sleep(2)

    logger.info("reward.redeemed consumer stopped")