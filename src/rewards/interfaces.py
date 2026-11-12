"""
src/rewards/interfaces.py
─────────────────────────
Abstract repository contract for reward categories, catalog, stock, and redemptions.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol

from src.rewards import schemas
from src.rewards.models import RewardCatalog, RewardCategory, RewardHistory


class IRewardRepository(Protocol):
    # ── Category Operations ───────────────────────────────────────────
    async def get_category_by_id(
        self, category_id: uuid.UUID
    ) -> RewardCategory | None: ...

    async def get_category_by_code(self, code: str) -> RewardCategory | None: ...

    async def list_categories(
        self, is_active: bool | None = None
    ) -> list[RewardCategory]: ...

    async def create_category(
        self, request: schemas.CreateCategoryRequest, user_id: uuid.UUID
    ) -> RewardCategory: ...

    async def update_category(
        self,
        category_id: uuid.UUID,
        update_data: dict[str, Any],
        user_id: uuid.UUID,
    ) -> RewardCategory | None: ...

    # ── Catalog Operations ────────────────────────────────────────────
    async def get_item_by_id(self, catalog_id: uuid.UUID) -> RewardCatalog | None: ...

    async def get_item_by_code(self, reward_code: str) -> RewardCatalog | None: ...

    async def list_catalog(
        self,
        is_active: bool | None,
        page: int,
        size: int,
    ) -> tuple[list[RewardCatalog], int]: ...

    async def create_item(
        self, item: schemas.CreateRewardRequest, user_id: uuid.UUID
    ) -> RewardCatalog: ...

    async def update_item(
        self,
        catalog_id: uuid.UUID,
        update_data: dict[str, Any],
        user_id: uuid.UUID,
    ) -> RewardCatalog | None: ...

    async def add_stock(
        self,
        catalog_id: uuid.UUID,
        amount: int,
        user_id: uuid.UUID,
    ) -> tuple[RewardCatalog | None, int]: ...

    # ── Redemption Operations ─────────────────────────────────────────
    async def claim_reward_atomic(
        self,
        catalog_id: uuid.UUID,
        wallet_id: uuid.UUID,
        points: int,
        granted_by_user_id: uuid.UUID,
        comment: str | None = None,
    ) -> tuple[RewardCatalog, RewardHistory]: ...

    async def list_history(
        self,
        wallet_id: uuid.UUID | None,
        page: int,
        size: int,
    ) -> tuple[list[RewardHistory], int]: ...