"""
src/wallet/router.py
────────────────────
FastAPI router for transactions and wallet balances.
Powered by WalletService with SQLAlchemy 2.0 async sessions.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from src.common.dependencies import CurrentUser, check_route_permission
from src.wallet import schemas
from src.wallet.dependencies import get_wallet_service
from src.wallet.service import WalletService

router = APIRouter()
transactions_router = APIRouter(prefix="/transactions", tags=["Transactions"])
wallets_router = APIRouter(tags=["Wallets"])


# ══════════════════════════════════════════════════════════════
#  Transactions Router
# ══════════════════════════════════════════════════════════════

@transactions_router.post("", response_model=schemas.TransactionResponse)
async def create_txn(
    request: Request,
    data: schemas.TransactionCreate,
    current_user: CurrentUser = Depends(check_route_permission),
    service: WalletService = Depends(get_wallet_service),
):
    return await service.create_transaction(data, current_user, request)


@transactions_router.get("/types", response_model=list[schemas.TransactionTypeInfo])
async def list_transaction_types(
    current_user: CurrentUser = Depends(check_route_permission),
    service: WalletService = Depends(get_wallet_service),
):
    return await service.get_transaction_types(current_user)


@transactions_router.get("", response_model=schemas.TransactionListResponse)
async def list_transactions(
    wallet_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    start_date: datetime | None = Query(None, description="Filter transactions after this date"),
    end_date: datetime | None = Query(None, description="Filter transactions before this date"),
    status_code: str | None = Query(None, description="Filter by status code"),
    current_user: CurrentUser = Depends(check_route_permission),
    service: WalletService = Depends(get_wallet_service),
):
    return await service.get_transactions(
        wallet_id=wallet_id,
        page=page,
        limit=limit,
        current_user=current_user,
        start_date=start_date,
        end_date=end_date,
        status_code=status_code,
    )


@transactions_router.get("/{transaction_id}", response_model=schemas.TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: WalletService = Depends(get_wallet_service),
):
    """Get a single transaction by ID with full details[cite: 28]."""
    return await service.get_transaction_by_id(transaction_id, current_user)


# ══════════════════════════════════════════════════════════════
#  Wallets Router
# ══════════════════════════════════════════════════════════════

@wallets_router.get("/employees/{employee_id}")
async def get_wallet(
    employee_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: WalletService = Depends(get_wallet_service),
):
    return await service.get_wallet_by_employee(employee_id, current_user)


@wallets_router.get("/{wallet_id}/balance", response_model=schemas.WalletBalanceResponse)
async def read_wallet_balance(
    wallet_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: WalletService = Depends(get_wallet_service),
):
    return await service.get_wallet_balance(wallet_id, current_user)


@wallets_router.get("/{wallet_id}/points-summary")
async def get_points_summary_route(
    wallet_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: WalletService = Depends(get_wallet_service),
):
    return await service.get_points_summary(wallet_id, current_user)


@wallets_router.post("/credit-from-review")
async def credit_from_review_route(
    review_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: WalletService = Depends(get_wallet_service),
):
    """
    Direct endpoint fallback for crediting wallet from review[cite: 28].
    Primary flow is handled asynchronously via the Redis consumer.
    """
    user_id = UUID(str(current_user.id))
    # Fallback placeholder resolving to service review credit
    return await service.credit_wallet_from_review(
        review_id=review_id,
        receiver_id=user_id,
        points=0,
        reviewer_id=user_id,
    )


router.include_router(transactions_router)
router.include_router(wallets_router)