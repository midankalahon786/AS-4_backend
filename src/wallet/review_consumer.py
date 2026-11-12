"""
src/wallet/review_consumer.py
──────────────────────────────
Redis Stream consumer — listens on 'events:review.created'
and credits points to the receiver's wallet[cite: 27].
Powered by SQLAlchemy 2.0 Async Session Factory.

Idempotency: Checks for an existing CREDIT transaction with
reference_number = review_id before writing[cite: 27].

Consumer group : wallet-service[cite: 27]
Consumer name  : review-credit-worker-1[cite: 27]
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
from src.employees.models import Employee, StatusMaster
from src.notifications.cache import enqueue_notification
from src.notifications.schemas import NotificationType
from src.notifications.service import NotificationService
from src.recognition.models import Review
from src.wallet.models import PointTransaction, TransactionType, Wallet

logger = logging.getLogger(__name__)

STREAM_KEY = "events:review.created"
GROUP_NAME = "wallet-service"
CONSUMER_NAME = "review-credit-worker-1"
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


async def _credit_points(
    review_id: UUID,
    receiver_id: UUID,
    raw_points: int,
    ip_address: str | None = None,
) -> None:
    """Credit raw_points to the receiver's wallet idempotently[cite: 27]."""
    ref_number = str(review_id)

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
            logger.debug("Transaction for review %s already exists — skipping", review_id)
            return

        # 2. Find Wallet
        wallet_stmt = select(Wallet).where(Wallet.employee_id == receiver_id)
        wallet = (await session.execute(wallet_stmt)).scalar_one_or_none()
        if not wallet:
            raise RuntimeError(f"Wallet not found for employee {receiver_id}")

        # 3. Resolve CREDIT transaction type
        credit_type_stmt = select(TransactionType).where(
            TransactionType.is_credit.is_(True),
            TransactionType.type_code == "REVIEW_CREDIT",
        )
        credit_type = (await session.execute(credit_type_stmt)).scalar_one_or_none()
        if not credit_type:
            fallback_stmt = select(TransactionType).where(TransactionType.is_credit.is_(True))
            credit_type = (await session.execute(fallback_stmt)).scalar_one_or_none()
        if not credit_type:
            raise RuntimeError("No credit transaction type found in transaction_types table")

        # 4. Resolve SUCCESS status
        status_stmt = select(StatusMaster).where(
            StatusMaster.status_code == "SUCCESS",
            StatusMaster.entity_type == "TRANSACTION",
        )
        status_rec = (await session.execute(status_stmt)).scalar_one_or_none()
        if not status_rec:
            fallback_status = select(StatusMaster).where(StatusMaster.status_code == "SUCCESS")
            status_rec = (await session.execute(fallback_status)).scalar_one_or_none()
        if not status_rec:
            raise RuntimeError("No SUCCESS status found in status_master table")

        # 5. Fetch Reviewer Name for ledger description
        rev_stmt = select(Employee.username).join(
            Review, Review.reviewer_id == Employee.employee_id
        ).where(Review.review_id == review_id)
        reviewer_name = (await session.execute(rev_stmt)).scalar_one_or_none() or "System"

        wallet_before = {
            "available_points": wallet.available_points,
            "total_earned_points": wallet.total_earned_points,
        }

        now = _now()
        new_txn = PointTransaction(
            wallet_id=wallet.wallet_id,
            amount=raw_points,
            transaction_type_id=credit_type.type_id,
            status_id=status_rec.status_id,
            reference_number=ref_number,
            description=f"Points credited from review by {reviewer_name}",
            transaction_at=now,
            created_by=receiver_id,
            updated_by=receiver_id,
            created_at=now,
            updated_at=now,
        )

        async with audit_ctx(
            user_id=str(receiver_id),
            request=None,
            ip_address=ip_address,
            table_name="transactions",
            record_id=lambda: str(new_txn.transaction_id),
            operation="CREDIT",
            old_values=wallet_before,
            new_values=lambda: {
                "available_points": wallet_before["available_points"] + raw_points,
                "total_earned_points": wallet_before["total_earned_points"] + raw_points,
                "points_credited": raw_points,
                "review_id": str(review_id),
                "reference": ref_number,
            },
        ):
            session.add(new_txn)

            # Atomic balance increment with optimistic lock check
            update_wallet_stmt = (
                update(Wallet)
                .where(Wallet.wallet_id == wallet.wallet_id, Wallet.version == wallet.version)
                .values(
                    available_points=Wallet.available_points + raw_points,
                    total_earned_points=Wallet.total_earned_points + raw_points,
                    version=Wallet.version + 1,
                    updated_by=receiver_id,
                    updated_at=now,
                )
            )
            update_res = await session.execute(update_wallet_stmt)
            if update_res.rowcount == 0:
                raise RuntimeError("Concurrent wallet update detected during review crediting")

            await session.commit()

        await cache_delete(f"wallets:employee:{receiver_id}")
        logger.info("Credited %d points to wallet %s for review %s", raw_points, wallet.wallet_id, review_id)

        # 6. Notifications
        try:
            from src.notifications.redis_client import get_redis
            try:
                r = get_redis()
            except RuntimeError:
                r = None

            notif_svc = NotificationService(session, redis=r)
            notif = await notif_svc.create_notification(
                employee_id=receiver_id,
                title="A Performance Review Has Been Submitted",
                message=(
                    "A new performance review has been submitted and recorded against "
                    "your employee profile on the Aabhar platform."
                ),
                type=NotificationType.REVIEW,
            )
            if r is not None and notif:
                await enqueue_notification(r, str(notif["notification_id"]))
        except Exception as _notif_exc:
            logger.warning("REVIEW notification failed for receiver %s: %s", receiver_id, _notif_exc)


async def _handle_message(r, msg_id: str, fields: dict) -> None:
    raw_review_id = fields.get("review_id", "")
    raw_receiver_id = fields.get("receiver_id", "")
    ip_address = fields.get("ip_address") or None
    try:
        raw_points = int(fields.get("raw_points", "0"))
    except ValueError:
        raw_points = 0

    if not raw_review_id or not raw_receiver_id:
        logger.warning("review.created msg %s missing fields — ACKing", msg_id)
        await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
        return

    try:
        await _credit_points(UUID(raw_review_id), UUID(raw_receiver_id), raw_points, ip_address)
        await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
    except RuntimeError as exc:
        err = str(exc).lower()
        if "not found" in err and "wallet" not in err:
            logger.error("Dead-letter: unrecoverable error crediting review %s: %s — ACKing", raw_review_id, exc)
            await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
        else:
            logger.error("Transient error crediting review %s: %s (will retry)", raw_review_id, exc)
    except Exception as exc:
        logger.error("Failed to credit review %s: %s", raw_review_id, exc)


async def _recover_pending(r) -> None:
    try:
        pending = await r.xpending_range(STREAM_KEY, GROUP_NAME, min="-", max="+", count=100)
        if not pending:
            return
        logger.info("Recovering %d pending review.created messages", len(pending))
        for entry in pending:
            msg_id = entry["message_id"]
            msgs = await r.xrange(STREAM_KEY, min=msg_id, max=msg_id)
            if msgs:
                _, fields = msgs[0]
                await _handle_message(r, msg_id, fields)
    except Exception as exc:
        logger.warning("review.created pending recovery failed: %s", exc)


async def review_created_consumer_loop(shutdown_event: asyncio.Event) -> None:
    from src.notifications.redis_client import get_redis

    try:
        r = get_redis()
    except RuntimeError:
        logger.warning("Redis not available — review.created consumer disabled")
        return

    await _ensure_group(r)
    await _recover_pending(r)
    logger.info("review.created consumer started ✅")

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
            logger.error("review.created consumer error: %s", exc)
            if "NOGROUP" in str(exc):
                try:
                    await _ensure_group(r)
                except Exception as eg_exc:
                    logger.error("review.created _ensure_group recovery failed: %s", eg_exc)
            await asyncio.sleep(2)

    logger.info("review.created consumer stopped")