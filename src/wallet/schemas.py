"""
src/wallet/schemas.py
─────────────────────
Pydantic v2 schemas for Wallets, Transactions, and Internal Aggregations.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ══════════════════════════════════════════════════════════════
#  Reference Info DTOs
# ══════════════════════════════════════════════════════════════

class StatusInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status_id: str
    code: str
    name: str


class TransactionTypeInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type_id: str
    code: str
    name: str
    is_credit: bool


# ══════════════════════════════════════════════════════════════
#  Transaction DTOs
# ══════════════════════════════════════════════════════════════

class TransactionCreate(BaseModel):
    wallet_id: UUID
    amount: int = Field(..., gt=0, description="Amount must be greater than zero")
    transaction_type_id: UUID
    description: str | None = None
    reference_number: str = Field(..., min_length=1, max_length=100)


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: UUID
    wallet_id: UUID
    amount: int
    status: StatusInfo
    transaction_type: TransactionTypeInfo
    reference_number: str | None = None
    description: str | None = None
    transaction_at: datetime
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None
    updated_by: UUID | None = None


class TransactionListResponse(BaseModel):
    page: int
    limit: int
    total: int
    transactions: list[TransactionResponse]


# ══════════════════════════════════════════════════════════════
#  Wallet DTOs
# ══════════════════════════════════════════════════════════════

class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_id: UUID
    employee_id: UUID
    available_points: int
    redeemed_points: int
    total_earned_points: int


class WalletBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_id: UUID
    available_points: int


class PointsSummaryResponse(BaseModel):
    wallet_id: UUID
    points_this_month: int
    points_this_year: int


class ReviewCreditRequest(BaseModel):
    employee_id: UUID
    rating: int
    review_id: UUID
    created_by: UUID


class ReviewCreditResponse(BaseModel):
    transaction_id: UUID
    wallet_id: UUID
    credited_points: int
    message: str


# ══════════════════════════════════════════════════════════════
#  Internal Router DTOs
# ══════════════════════════════════════════════════════════════

class WalletStatsResponse(BaseModel):
    available_points: int
    total_earned_points: int
    pts_this_month: int
    pts_last_month: int
    rewards_total: int
    rewards_this_month: int
    rewards_last_month: int


class LeaderboardEntry(BaseModel):
    rank: int
    employee_id: UUID
    username: str
    department: str
    total_earned_points: int