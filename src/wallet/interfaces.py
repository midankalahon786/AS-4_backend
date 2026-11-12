"""
src/wallet/interfaces.py
────────────────────────
Abstract repository contract for wallets, transactions, transaction types,
and optimistic concurrency control.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from src.wallet.models import PointTransaction, TransactionType, Wallet


class IWalletRepository(Protocol):
    # ── Transaction Types ────────────────────────────────────────────
    async def list_transaction_types(self) -> list[TransactionType]: ...

    async def get_transaction_type_by_id(
        self, type_id: uuid.UUID
    ) -> TransactionType | None: ...

    async def get_transaction_type_by_code(
        self, code: str
    ) -> TransactionType | None: ...

    # ── Status Master Helper ─────────────────────────────────────────
    async def get_status_by_code(self, status_code: str) -> uuid.UUID | None: ...

    # ── Wallet Lookups ───────────────────────────────────────────────
    async def get_wallet_by_id(self, wallet_id: uuid.UUID) -> Wallet | None: ...

    async def get_wallet_by_employee_id(
        self, employee_id: uuid.UUID
    ) -> Wallet | None: ...

    async def create_wallet(
        self,
        employee_id: uuid.UUID,
        initial_points: int = 0,
        created_by_id: uuid.UUID | None = None,
    ) -> Wallet: ...

    # ── Atomic Mutations (Optimistic Locking via `version`) ──────────
    async def create_manual_transaction_atomic(
        self,
        wallet_id: uuid.UUID,
        amount: int,
        is_credit: bool,
        expected_version: int,
        transaction_type_id: uuid.UUID,
        status_id: uuid.UUID,
        description: str | None,
        reference_number: str | None,
        created_by: uuid.UUID,
    ) -> PointTransaction: ...

    async def credit_from_review_atomic(
        self,
        wallet_id: uuid.UUID,
        points: int,
        expected_version: int,
        transaction_type_id: uuid.UUID,
        status_id: uuid.UUID,
        description: str,
        reference_number: str,
        created_by: uuid.UUID,
    ) -> PointTransaction: ...

    async def adjust_for_review_update_atomic(
        self,
        wallet_id: uuid.UUID,
        int_delta: int,
        expected_version: int,
        transaction_type_id: uuid.UUID,
        status_id: uuid.UUID,
        description: str,
        reference_number: str,
        updated_by: uuid.UUID,
    ) -> PointTransaction: ...

    # ── Transaction Queries ──────────────────────────────────────────
    async def get_transactions(
        self,
        wallet_id: uuid.UUID,
        offset: int,
        limit: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        status_id: uuid.UUID | None = None,
    ) -> tuple[list[PointTransaction], int]: ...

    async def get_transaction_by_id(
        self, transaction_id: uuid.UUID
    ) -> PointTransaction | None: ...

    async def get_points_summary(
        self, wallet_id: uuid.UUID
    ) -> tuple[int, int]: ...