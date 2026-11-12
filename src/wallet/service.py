"""
src/wallet/service.py
─────────────────────
Wallet domain service managing transactions, balances, manual entries,
review credits, and adjustments.
Decoupled via IWalletRepository.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from src.common.audit import audit_ctx
from src.common.cache import (
    L1_PERMANENT,
    L1_VOLATILE,
    TTL_PERMANENT,
    TTL_VOLATILE,
    cache_delete,
    cache_get,
    cache_set,
)
from src.common.dependencies import CurrentUser
from src.notifications.schemas import NotificationType
from src.notifications.service import NotificationService
from src.wallet import schemas
from src.wallet.interfaces import IWalletRepository

logger = logging.getLogger(__name__)

_KEY_TXN_TYPES = "wallet:transaction_types"


def _wallet_key(employee_id: UUID) -> str:
    return f"wallets:employee:{employee_id}"


WNF = "Wallet not found"
AD = "Access Denied"


def is_admin(user: CurrentUser) -> bool:
    return any(role in user.roles for role in ["HR_ADMIN", "SUPER_ADMIN"])


class WalletService:
    def __init__(
        self,
        repo: IWalletRepository,
        notif_service: NotificationService | None = None,
    ) -> None:
        self.repo = repo
        self.notif_service = notif_service

    # ── Transaction Types ────────────────────────────────────────────

    async def get_transaction_types(
        self, current_user: CurrentUser
    ) -> list[dict[str, Any]]:
        cached = await cache_get(_KEY_TXN_TYPES, l1_ttl=L1_PERMANENT)
        if cached is not None:
            return cached

        types = await self.repo.list_transaction_types()
        data = [
            {
                "type_id": str(t.type_id),
                "code": t.type_code,
                "name": t.type_name,
                "is_credit": t.is_credit,
            }
            for t in types
        ]
        await cache_set(_KEY_TXN_TYPES, data, ttl=TTL_PERMANENT, l1_ttl=L1_PERMANENT)
        return data

    # ── Manual Transactions ──────────────────────────────────────────

    async def create_transaction(
        self,
        data: Any,
        current_user: CurrentUser,
        request: Request | None = None,
    ) -> dict[str, Any]:
        if not is_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to create transactions",
            )

        wallet_id = UUID(str(data.wallet_id))
        txn_type_id = UUID(str(data.transaction_type_id))
        created_by = UUID(str(current_user.id))
        amount = int(data.amount)

        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount must be greater than zero",
            )

        wallet = await self.repo.get_wallet_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WNF)

        txn_type = await self.repo.get_transaction_type_by_id(txn_type_id)
        if not txn_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Transaction type not found"
            )

        success_status_id = await self.repo.get_status_by_code("APPROVED")
        if not success_status_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="APPROVED status not found in status_master",
            )

        if not txn_type.is_credit and wallet.available_points < amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient wallet balance"
            )

        new_txn = None
        try:
            async with audit_ctx(
                user_id=str(created_by),
                request=request,
                table_name="transactions",
                record_id=lambda: str(new_txn.transaction_id) if new_txn else "",
                operation="INSERT",
                new_values=lambda: {
                    "wallet_id": str(wallet_id),
                    "amount": amount,
                    "type_code": txn_type.type_code,
                    "is_credit": txn_type.is_credit,
                    "reference_number": data.reference_number,
                },
            ):
                new_txn = await self.repo.create_manual_transaction_atomic(
                    wallet_id=wallet_id,
                    amount=amount,
                    is_credit=txn_type.is_credit,
                    expected_version=wallet.version,
                    transaction_type_id=txn_type_id,
                    status_id=success_status_id,
                    description=data.description,
                    reference_number=data.reference_number,
                    created_by=created_by,
                )

            await cache_delete(_wallet_key(wallet.employee_id))

            if self.notif_service:
                try:
                    direction = "credited to" if txn_type.is_credit else "debited from"
                    await self.notif_service.create_notification(
                        employee_id=wallet.employee_id,
                        title=f"{amount} points {direction} your wallet",
                        message=(
                            f"{amount} points have been {direction} your wallet "
                            f"via {txn_type.type_name}."
                            + (f" — {data.description}" if data.description else "")
                            + (f" (Ref: {data.reference_number})" if data.reference_number else "")
                        ),
                        type=NotificationType.REWARD,
                    )
                except Exception:
                    logger.exception(
                        "Transaction notification failed for txn %s", new_txn.transaction_id
                    )

            return self._format_transaction(new_txn)

        except ValueError as ve:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transaction with this reference number already exists",
            )

    # ── Transaction Listing ──────────────────────────────────────────

    async def get_transactions(
        self,
        wallet_id: UUID,
        page: int,
        limit: int,
        current_user: CurrentUser,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        status_code: str | None = None,
    ) -> dict[str, Any]:
        wallet = await self.repo.get_wallet_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WNF)

        user_id = UUID(str(current_user.id))
        if not is_admin(current_user) and wallet.employee_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=AD)

        page = max(page, 1)
        limit = min(max(limit, 1), 100)
        offset = (page - 1) * limit

        status_id = None
        if status_code:
            status_id = await self.repo.get_status_by_code(status_code)

        txns, total = await self.repo.get_transactions(
            wallet_id=wallet_id,
            offset=offset,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            status_id=status_id,
        )

        formatted = [self._format_transaction(txn) for txn in txns]
        return {"page": page, "limit": limit, "total": total, "transactions": formatted}

    async def get_transaction_by_id(
        self, transaction_id: UUID, current_user: CurrentUser
    ) -> dict[str, Any]:
        txn = await self.repo.get_transaction_by_id(transaction_id)
        if not txn:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
            )

        user_id = UUID(str(current_user.id))
        if not is_admin(current_user):
            wallet = await self.repo.get_wallet_by_id(txn.wallet_id)
            if not wallet or wallet.employee_id != user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=AD)

        return self._format_transaction(txn)

    # ── Wallet Lookups ───────────────────────────────────────────────

    async def get_wallet_by_employee(
        self, employee_id: UUID, current_user: CurrentUser
    ) -> dict[str, Any]:
        user_id = UUID(str(current_user.id))
        if not is_admin(current_user) and employee_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=AD)

        key = _wallet_key(employee_id)
        cached = await cache_get(key, l1_ttl=L1_VOLATILE)
        if cached is not None:
            return cached

        wallet = await self.repo.get_wallet_by_employee_id(employee_id)
        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WNF)

        data = {
            "wallet_id": str(wallet.wallet_id),
            "employee_id": str(wallet.employee_id),
            "available_points": wallet.available_points,
            "redeemed_points": wallet.redeemed_points,
            "total_earned_points": wallet.total_earned_points,
            "version": wallet.version,
            "created_at": wallet.created_at.isoformat(),
            "updated_at": wallet.updated_at.isoformat(),
        }
        await cache_set(key, data, ttl=TTL_VOLATILE, l1_ttl=L1_VOLATILE)
        return data

    async def get_wallet_balance(
        self, wallet_id: UUID, current_user: CurrentUser
    ) -> dict[str, Any]:
        wallet = await self.repo.get_wallet_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WNF)

        user_id = UUID(str(current_user.id))
        if not is_admin(current_user) and wallet.employee_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=AD)

        return {
            "wallet_id": str(wallet.wallet_id),
            "available_points": wallet.available_points,
        }

    async def get_points_summary(
        self, wallet_id: UUID, current_user: CurrentUser
    ) -> dict[str, Any]:
        wallet = await self.repo.get_wallet_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WNF)

        user_id = UUID(str(current_user.id))
        if not is_admin(current_user) and wallet.employee_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=AD)

        points_this_month, points_this_year = await self.repo.get_points_summary(wallet_id)
        return {
            "wallet_id": str(wallet_id),
            "points_this_month": points_this_month,
            "points_this_year": points_this_year,
        }

    # ── Review Credits & Adjustments ─────────────────────────────────

    async def credit_wallet_from_review(
        self,
        review_id: UUID,
        receiver_id: UUID,
        points: int,
        reviewer_id: UUID,
        category_label: str = "REVIEW",
        reviewer_name: str = "Anonymous",
    ) -> dict[str, Any]:
        if points <= 0:
            return {"message": "No points awarded for this rating", "credited_points": 0}

        wallet = await self.repo.get_wallet_by_employee_id(receiver_id)
        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WNF)

        txn_type = await self.repo.get_transaction_type_by_code("CREDIT")
        if not txn_type:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="CREDIT transaction type missing",
            )

        status_id = await self.repo.get_status_by_code("APPROVED")
        if not status_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="APPROVED status not found",
            )

        reference = f"REVIEW-{review_id}"
        description = f"{category_label} from {reviewer_name} → {points} pts"

        new_txn = None
        try:
            async with audit_ctx(
                user_id=str(reviewer_id),
                request=None,
                table_name="transactions",
                record_id=lambda: str(new_txn.transaction_id) if new_txn else "",
                operation="CREDIT",
                new_values=lambda: {
                    "wallet_id": str(wallet.wallet_id),
                    "employee_id": str(receiver_id),
                    "points": points,
                    "review_id": str(review_id),
                    "category_label": category_label,
                    "reference": reference,
                },
            ):
                new_txn = await self.repo.credit_from_review_atomic(
                    wallet_id=wallet.wallet_id,
                    points=points,
                    expected_version=wallet.version,
                    transaction_type_id=txn_type.type_id,
                    status_id=status_id,
                    description=description,
                    reference_number=reference,
                    created_by=reviewer_id,
                )

            await cache_delete(_wallet_key(receiver_id))

            if self.notif_service:
                try:
                    await self.notif_service.create_notification(
                        employee_id=receiver_id,
                        title=f"{points} points credited to your wallet",
                        message=(
                            f"You earned {points} pts for a {category_label} review. "
                            f"New balance: {wallet.available_points + points} pts."
                        ),
                        type=NotificationType.REWARD,
                    )
                except Exception:
                    logger.exception("Credit notification failed for review %s", review_id)

            return {
                "transaction_id": str(new_txn.transaction_id),
                "wallet_id": str(wallet.wallet_id),
                "credited_points": points,
                "new_balance": wallet.available_points + points,
                "message": f"{points} points credited successfully",
            }

        except ValueError as ve:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Points already credited for this review",
            )

    async def adjust_wallet_for_review_update(
        self,
        review_id: UUID,
        receiver_id: UUID,
        delta_points: float,
        updated_by_id: UUID,
    ) -> dict[str, Any]:
        int_delta = round(delta_points)
        if int_delta == 0:
            return {
                "message": "No wallet adjustment needed (delta rounds to zero)",
                "credited_points": 0,
                "new_balance": None,
            }

        wallet = await self.repo.get_wallet_by_employee_id(receiver_id)
        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WNF)

        if int_delta < 0 and wallet.available_points + int_delta < 0:
            logger.warning(
                "Skipping wallet debit for review update %s — would go negative "
                "(available=%d delta=%d)",
                review_id,
                wallet.available_points,
                int_delta,
            )
            return {
                "message": "Wallet debit skipped — insufficient balance",
                "credited_points": int_delta,
                "new_balance": wallet.available_points,
            }

        type_code = "CREDIT" if int_delta > 0 else "DEBIT"
        txn_type = await self.repo.get_transaction_type_by_code(type_code)
        if not txn_type:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{type_code} transaction type missing",
            )

        status_id = await self.repo.get_status_by_code("APPROVED")
        if not status_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="APPROVED status not found",
            )

        now = datetime.now(timezone.utc)
        reference = f"REVIEW-UPDATE-{review_id}-{now.strftime('%Y%m%dT%H%M%S')}"
        direction_word = "adjusted +" if int_delta > 0 else "adjusted "
        description = (
            f"Review update → wallet {direction_word}{int_delta:+d} pts "
            f"(raw delta={delta_points:+.4f})"
        )

        new_txn = None
        try:
            async with audit_ctx(
                user_id=str(updated_by_id),
                request=None,
                table_name="transactions",
                record_id=lambda: str(new_txn.transaction_id) if new_txn else "",
                operation="ADJUST",
                new_values=lambda: {
                    "wallet_id": str(wallet.wallet_id),
                    "employee_id": str(receiver_id),
                    "delta": int_delta,
                    "review_id": str(review_id),
                    "reference": reference,
                },
            ):
                new_txn = await self.repo.adjust_for_review_update_atomic(
                    wallet_id=wallet.wallet_id,
                    int_delta=int_delta,
                    expected_version=wallet.version,
                    transaction_type_id=txn_type.type_id,
                    status_id=status_id,
                    description=description,
                    reference_number=reference,
                    updated_by=updated_by_id,
                )

            await cache_delete(_wallet_key(receiver_id))

            if self.notif_service:
                try:
                    emoji = "💰" if int_delta > 0 else "📉"
                    await self.notif_service.create_notification(
                        employee_id=receiver_id,
                        title=f"Your wallet was adjusted {emoji}",
                        message=(
                            f"A review you received was updated. "
                            f"Your wallet was adjusted by {int_delta:+d} pts. "
                            f"New balance: {wallet.available_points + int_delta} pts."
                        ),
                        type=NotificationType.REWARD,
                    )
                except Exception:
                    logger.exception(
                        "Adjustment notification failed for review update %s", review_id
                    )

            return {
                "transaction_id": str(new_txn.transaction_id),
                "wallet_id": str(wallet.wallet_id),
                "credited_points": int_delta,
                "new_balance": wallet.available_points + int_delta,
                "message": f"Wallet adjusted by {int_delta:+d} points",
            }

        except ValueError as ve:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Wallet adjustment already recorded for this review update",
            )
            

    @staticmethod
    def _format_transaction(txn: Any) -> dict[str, Any]:
        return {
            "transaction_id": str(txn.transaction_id),
            "wallet_id": str(txn.wallet_id),
            "amount": txn.amount,
            "status": {
                "status_id": str(txn.status_master.status_id) if txn.status_master else None,
                "code": txn.status_master.status_code if txn.status_master else "UNKNOWN",
                "name": txn.status_master.status_name if txn.status_master else "UNKNOWN",
            },
            "transaction_type": {
                "type_id": str(txn.transaction_type.type_id) if txn.transaction_type else None,
                "code": txn.transaction_type.type_code if txn.transaction_type else "UNKNOWN",
                "name": txn.transaction_type.type_name if txn.transaction_type else "UNKNOWN",
                "is_credit": txn.transaction_type.is_credit if txn.transaction_type else True,
            },
            "reference_number": txn.reference_number,
            "description": txn.description,
            "transaction_at": txn.transaction_at.isoformat() if txn.transaction_at else None,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
            "updated_at": txn.updated_at.isoformat() if txn.updated_at else None,
            "created_by": str(txn.created_by) if txn.created_by else None,
            "updated_by": str(txn.updated_by) if txn.updated_by else None,
        }