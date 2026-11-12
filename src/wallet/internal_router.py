"""
src/wallet/internal_router.py
──────────────────────────────
Internal-only endpoints consumed by Analytics and Rewards services.
Mounted with NO APIRouter prefix[cite: 27].
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.wallet.dependencies import get_wallet_service
from src.wallet.service import WalletService

router = APIRouter(tags=["Internal"])


@router.get("/internal/employees/{employee_id}/manager-email")
async def get_manager_email(
    employee_id: UUID,
    service: WalletService = Depends(get_wallet_service),
):
    """
    Returns {"email": "manager@example.com"} if the employee has a manager[cite: 27].
    """
    email = await service.repo.get_manager_email(employee_id)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manager or employee not found",
        )
    return {"email": email}


@router.get("/internal/wallets/by-employee/{employee_id}")
async def get_wallet_by_employee(
    employee_id: UUID,
    service: WalletService = Depends(get_wallet_service),
):
    wallet = await service.repo.get_wallet_by_employee_id(employee_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        )
    return {
        "wallet_id": str(wallet.wallet_id),
        "employee_id": str(employee_id),
        "available_points": wallet.available_points,
        "redeemed_points": wallet.redeemed_points,
        "total_earned_points": wallet.total_earned_points,
    }


@router.get("/internal/wallets/by-id/{wallet_id}")
async def get_wallet_by_id(
    wallet_id: UUID,
    service: WalletService = Depends(get_wallet_service),
):
    wallet = await service.repo.get_wallet_by_id(wallet_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        )
    return {
        "wallet_id": str(wallet.wallet_id),
        "employee_id": str(wallet.employee_id),
        "available_points": wallet.available_points,
    }


@router.get("/internal/wallets/stats")
async def get_wallet_stats(
    employee_id: UUID | None = Query(None),
    service: WalletService = Depends(get_wallet_service),
):
    return await service.repo.get_wallet_stats(employee_id)


@router.get("/internal/wallets/stats/batch")
async def get_wallet_stats_batch(
    employee_ids: str = Query(...),
    service: WalletService = Depends(get_wallet_service),
):
    """
    Bulk wallet stats for a comma-separated list of employee_ids[cite: 27].
    """
    ids = [UUID(eid.strip()) for eid in employee_ids.split(",") if eid.strip()]
    return await service.repo.get_wallet_stats_batch(ids)


@router.get("/internal/wallets/leaderboard")
async def get_leaderboard(
    limit: int = Query(10, ge=1, le=50),
    service: WalletService = Depends(get_wallet_service),
):
    return await service.repo.get_leaderboard(limit)