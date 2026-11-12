"""
src/rewards/repository.py
─────────────────────────
SQLAlchemy 2.0 implementation of IRewardRepository.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.rewards import schemas
from src.rewards.models import RewardCatalog, RewardCategory, RewardHistory
from src.wallet.models import Wallet


class SQLAlchemyRewardRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Category Operations ───────────────────────────────────────────

    async def get_category_by_id(
        self, category_id: uuid.UUID
    ) -> RewardCategory | None:
        stmt = select(RewardCategory).where(
            RewardCategory.category_id == category_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_category_by_code(self, code: str) -> RewardCategory | None:
        stmt = select(RewardCategory).where(
            RewardCategory.category_code == code.strip().upper()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_categories(
        self, is_active: bool | None = None
    ) -> list[RewardCategory]:
        stmt = select(RewardCategory)
        if is_active is not None:
            stmt = stmt.where(RewardCategory.is_active.is_(is_active))
        stmt = stmt.order_by(RewardCategory.category_name.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def create_category(
        self, request: schemas.CreateCategoryRequest, user_id: uuid.UUID
    ) -> RewardCategory:
        now = datetime.now(timezone.utc)
        cat = RewardCategory(
            category_name=request.category_name,
            category_code=request.category_code,
            description=request.description,
            is_active=True,
            created_by=user_id,
            updated_by=user_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(cat)
        await self.db.flush()
        return cat

    async def update_category(
        self,
        category_id: uuid.UUID,
        update_data: dict[str, Any],
        user_id: uuid.UUID,
    ) -> RewardCategory | None:
        now = datetime.now(timezone.utc)
        update_data["updated_by"] = user_id
        update_data["updated_at"] = now

        stmt = (
            update(RewardCategory)
            .where(RewardCategory.category_id == category_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)
        return await self.get_category_by_id(category_id)

    # ── Catalog Operations ────────────────────────────────────────────

    async def get_item_by_id(self, catalog_id: uuid.UUID) -> RewardCatalog | None:
        stmt = (
            select(RewardCatalog)
            .options(joinedload(RewardCatalog.category))
            .where(RewardCatalog.catalog_id == catalog_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_item_by_code(self, reward_code: str) -> RewardCatalog | None:
        stmt = select(RewardCatalog).where(
            RewardCatalog.reward_code == reward_code.strip().upper()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_catalog(
        self,
        is_active: bool | None,
        page: int,
        size: int,
    ) -> tuple[list[RewardCatalog], int]:
        stmt = select(RewardCatalog).options(joinedload(RewardCatalog.category))
        if is_active is not None:
            stmt = stmt.where(RewardCatalog.is_active.is_(is_active))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0
        offset = (page - 1) * size

        ordered_stmt = (
            stmt.order_by(RewardCatalog.created_at.desc()).offset(offset).limit(size)
        )
        rows = list((await self.db.execute(ordered_stmt)).scalars().all())
        return rows, total

    async def create_item(
        self, item: schemas.CreateRewardRequest, user_id: uuid.UUID
    ) -> RewardCatalog:
        now = datetime.now(timezone.utc)
        record = RewardCatalog(
            reward_name=item.reward_name,
            reward_code=item.reward_code,
            description=item.description,
            category_id=item.category_id,
            default_points=item.default_points,
            min_points=item.min_points,
            max_points=item.max_points,
            available_stock=item.available_stock or 0,
            is_active=True,
            created_by=user_id,
            updated_by=user_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        return await self.get_item_by_id(record.catalog_id)  # type: ignore

    async def update_item(
        self,
        catalog_id: uuid.UUID,
        update_data: dict[str, Any],
        user_id: uuid.UUID,
    ) -> RewardCatalog | None:
        now = datetime.now(timezone.utc)
        update_data["updated_by"] = user_id
        update_data["updated_at"] = now

        stmt = (
            update(RewardCatalog)
            .where(RewardCatalog.catalog_id == catalog_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)
        return await self.get_item_by_id(catalog_id)

    async def add_stock(
        self,
        catalog_id: uuid.UUID,
        amount: int,
        user_id: uuid.UUID,
    ) -> tuple[RewardCatalog | None, int]:
        item = await self.get_item_by_id(catalog_id)
        if not item:
            return None, 0

        old_stock = item.available_stock
        now = datetime.now(timezone.utc)

        stmt = (
            update(RewardCatalog)
            .where(RewardCatalog.catalog_id == catalog_id)
            .values(
                available_stock=RewardCatalog.available_stock + amount,
                updated_by=user_id,
                updated_at=now,
            )
        )
        await self.db.execute(stmt)
        refreshed = await self.get_item_by_id(catalog_id)
        return refreshed, old_stock

    # ── Redemption Operations ─────────────────────────────────────────

    async def claim_reward_atomic(
        self,
        catalog_id: uuid.UUID,
        wallet_id: uuid.UUID,
        points: int,
        granted_by_user_id: uuid.UUID,
        comment: str | None = None,
    ) -> tuple[RewardCatalog, RewardHistory]:
        now = datetime.now(timezone.utc)

        # Atomic stock decrement guard against negative balances
        stock_stmt = (
            update(RewardCatalog)
            .where(
                RewardCatalog.catalog_id == catalog_id,
                RewardCatalog.available_stock > 0,
            )
            .values(
                available_stock=RewardCatalog.available_stock - 1,
                updated_by=granted_by_user_id,
                updated_at=now,
            )
            .returning(RewardCatalog)
        )
        res = await self.db.execute(stock_stmt)
        updated_catalog = res.scalar_one_or_none()
        if not updated_catalog:
            raise ValueError("Out of stock! This reward was just claimed by someone else.")

        history = RewardHistory(
            wallet_id=wallet_id,
            catalog_id=catalog_id,
            points=points,
            granted_by=granted_by_user_id,
            comment=comment,
            granted_at=now,
            created_by=granted_by_user_id,
            updated_by=granted_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(history)
        await self.db.flush()
        return updated_catalog, history

    async def list_history(
        self,
        wallet_id: uuid.UUID | None,
        page: int,
        size: int,
    ) -> tuple[list[RewardHistory], int]:
        stmt = select(RewardHistory).options(
            joinedload(RewardHistory.catalog_item),
            joinedload(RewardHistory.granted_by_employee),
        )
        if wallet_id:
            stmt = stmt.where(RewardHistory.wallet_id == wallet_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0
        offset = (page - 1) * size

        ordered_stmt = (
            stmt.order_by(RewardHistory.granted_at.desc()).offset(offset).limit(size)
        )
        rows = list((await self.db.execute(ordered_stmt)).scalars().all())
        return rows, total

    # ── Wallet Operations (Direct DB Fallback) ────────────────────────

    async def get_wallet_by_employee_id(self, employee_id: uuid.UUID) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.employee_id == employee_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_wallet_by_id(self, wallet_id: uuid.UUID) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.wallet_id == wallet_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()
