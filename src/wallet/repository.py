"""
src/wallet/repository.py
────────────────────────
SQLAlchemy 2.0 implementation of IWalletRepository.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from typing import Any
from dateutil.relativedelta import relativedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.employees.models import StatusMaster, Employee
from src.wallet.models import PointTransaction, TransactionType, Wallet
from src.rewards.models import RewardHistory
from src.organization.models import Department


class SQLAlchemyWalletRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Transaction Types ────────────────────────────────────────────

    async def list_transaction_types(self) -> list[TransactionType]:
        stmt = select(TransactionType).order_by(TransactionType.type_name.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_transaction_type_by_id(
        self, type_id: uuid.UUID
    ) -> TransactionType | None:
        stmt = select(TransactionType).where(TransactionType.type_id == type_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_transaction_type_by_code(
        self, code: str
    ) -> TransactionType | None:
        stmt = select(TransactionType).where(
            func.upper(TransactionType.type_code) == code.strip().upper()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ── Status Master Helper ─────────────────────────────────────────

    async def get_status_by_code(self, status_code: str) -> uuid.UUID | None:
        stmt = select(StatusMaster.status_id).where(
            func.upper(StatusMaster.status_code) == status_code.strip().upper()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ── Wallet Lookups ───────────────────────────────────────────────

    async def get_wallet_by_id(self, wallet_id: uuid.UUID) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.wallet_id == wallet_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_wallet_by_employee_id(
        self, employee_id: uuid.UUID
    ) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.employee_id == employee_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create_wallet(
        self,
        employee_id: uuid.UUID,
        initial_points: int = 0,
        created_by_id: uuid.UUID | None = None,
    ) -> Wallet:
        now = datetime.now(timezone.utc)
        wallet = Wallet(
            employee_id=employee_id,
            available_points=initial_points,
            redeemed_points=0,
            total_earned_points=initial_points,
            version=1,
            created_by=created_by_id,
            updated_by=created_by_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(wallet)
        await self.db.flush()
        return wallet

    # ── Atomic Mutations ─────────────────────────────────────────────

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
    ) -> PointTransaction:
        now = datetime.now(timezone.utc)

        # 1. Update wallet version optimistically
        update_values = {
            "version": expected_version + 1,
            "updated_by": created_by,
            "updated_at": now,
        }
        if is_credit:
            update_values["available_points"] = Wallet.available_points + amount
            update_values["total_earned_points"] = Wallet.total_earned_points + amount
        else:
            update_values["available_points"] = Wallet.available_points - amount
            update_values["redeemed_points"] = Wallet.redeemed_points + amount

        wallet_stmt = (
            update(Wallet)
            .where(
                Wallet.wallet_id == wallet_id,
                Wallet.version == expected_version,
            )
            .values(**update_values)
            .returning(Wallet)
        )
        updated_wallet = (await self.db.execute(wallet_stmt)).scalar_one_or_none()
        if not updated_wallet:
            raise ValueError("OptimisticLockError: Wallet updated concurrently")

        # 2. Insert transaction entry
        txn = PointTransaction(
            wallet_id=wallet_id,
            amount=amount,
            transaction_type_id=transaction_type_id,
            status_id=status_id,
            description=description,
            reference_number=reference_number,
            transaction_at=now,
            created_by=created_by,
            updated_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(txn)
        await self.db.flush()

        # Eager load relationships for response serialization
        fetch_stmt = (
            select(PointTransaction)
            .options(
                joinedload(PointTransaction.status_master),
                joinedload(PointTransaction.transaction_type),
            )
            .where(PointTransaction.transaction_id == txn.transaction_id)
        )
        return (await self.db.execute(fetch_stmt)).scalar_one()

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
    ) -> PointTransaction:
        now = datetime.now(timezone.utc)

        wallet_stmt = (
            update(Wallet)
            .where(
                Wallet.wallet_id == wallet_id,
                Wallet.version == expected_version,
            )
            .values(
                available_points=Wallet.available_points + points,
                total_earned_points=Wallet.total_earned_points + points,
                version=expected_version + 1,
                updated_by=created_by,
                updated_at=now,
            )
            .returning(Wallet)
        )
        updated_wallet = (await self.db.execute(wallet_stmt)).scalar_one_or_none()
        if not updated_wallet:
            raise ValueError("OptimisticLockError: Wallet updated concurrently")

        txn = PointTransaction(
            wallet_id=wallet_id,
            amount=points,
            transaction_type_id=transaction_type_id,
            status_id=status_id,
            description=description,
            reference_number=reference_number,
            transaction_at=now,
            created_by=created_by,
            updated_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(txn)
        await self.db.flush()

        fetch_stmt = (
            select(PointTransaction)
            .options(
                joinedload(PointTransaction.status_master),
                joinedload(PointTransaction.transaction_type),
            )
            .where(PointTransaction.transaction_id == txn.transaction_id)
        )
        return (await self.db.execute(fetch_stmt)).scalar_one()

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
    ) -> PointTransaction:
        now = datetime.now(timezone.utc)
        abs_delta = abs(int_delta)

        update_vals = {
            "available_points": Wallet.available_points + int_delta,
            "version": expected_version + 1,
            "updated_by": updated_by,
            "updated_at": now,
        }
        if int_delta > 0:
            update_vals["total_earned_points"] = Wallet.total_earned_points + int_delta

        wallet_stmt = (
            update(Wallet)
            .where(
                Wallet.wallet_id == wallet_id,
                Wallet.version == expected_version,
            )
            .values(**update_vals)
            .returning(Wallet)
        )
        updated_wallet = (await self.db.execute(wallet_stmt)).scalar_one_or_none()
        if not updated_wallet:
            raise ValueError("OptimisticLockError: Wallet updated concurrently")

        txn = PointTransaction(
            wallet_id=wallet_id,
            amount=abs_delta,
            transaction_type_id=transaction_type_id,
            status_id=status_id,
            description=description,
            reference_number=reference_number,
            transaction_at=now,
            created_by=updated_by,
            updated_by=updated_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(txn)
        await self.db.flush()

        fetch_stmt = (
            select(PointTransaction)
            .options(
                joinedload(PointTransaction.status_master),
                joinedload(PointTransaction.transaction_type),
            )
            .where(PointTransaction.transaction_id == txn.transaction_id)
        )
        return (await self.db.execute(fetch_stmt)).scalar_one()

    # ── Transaction Queries ──────────────────────────────────────────

    async def get_transactions(
        self,
        wallet_id: uuid.UUID,
        offset: int,
        limit: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        status_id: uuid.UUID | None = None,
    ) -> tuple[list[PointTransaction], int]:
        stmt = (
            select(PointTransaction)
            .options(
                joinedload(PointTransaction.status_master),
                joinedload(PointTransaction.transaction_type),
            )
            .where(PointTransaction.wallet_id == wallet_id)
        )

        filters = []
        if start_date:
            filters.append(PointTransaction.transaction_at >= start_date)
        if end_date:
            filters.append(PointTransaction.transaction_at <= end_date)
        if status_id:
            filters.append(PointTransaction.status_id == status_id)

        if filters:
            stmt = stmt.where(*filters)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        ordered_stmt = (
            stmt.order_by(PointTransaction.transaction_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = list((await self.db.execute(ordered_stmt)).scalars().all())
        return rows, total

    async def get_transaction_by_id(
        self, transaction_id: uuid.UUID
    ) -> PointTransaction | None:
        stmt = (
            select(PointTransaction)
            .options(
                joinedload(PointTransaction.status_master),
                joinedload(PointTransaction.transaction_type),
            )
            .where(PointTransaction.transaction_id == transaction_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_points_summary(
        self, wallet_id: uuid.UUID
    ) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        month_stmt = select(
            func.coalesce(func.sum(PointTransaction.amount), 0)
        ).where(
            PointTransaction.wallet_id == wallet_id,
            PointTransaction.transaction_at >= start_of_month,
        )

        year_stmt = select(
            func.coalesce(func.sum(PointTransaction.amount), 0)
        ).where(
            PointTransaction.wallet_id == wallet_id,
            PointTransaction.transaction_at >= start_of_year,
        )

        month_sum = (await self.db.execute(month_stmt)).scalar() or 0
        year_sum = (await self.db.execute(year_stmt)).scalar() or 0
        return int(month_sum), int(year_sum)

    async def get_manager_email(self, employee_id: uuid.UUID) -> str | None:
        mgr_query = select(Employee.email).where(
            Employee.employee_id == (
                select(Employee.manager_id)
                .where(Employee.employee_id == employee_id)
                .scalar_subquery()
            )
        )
        return (await self.db.execute(mgr_query)).scalar_one_or_none()

    async def get_wallet_stats(self, employee_id: uuid.UUID | None = None) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        start_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_this = start_this + relativedelta(months=1)
        start_last = start_this - relativedelta(months=1)
        end_last = start_this

        # Credits this month & last month
        credit_type_ids_stmt = select(TransactionType.type_id).where(TransactionType.is_credit.is_(True))
        credit_ids = list((await self.db.execute(credit_type_ids_stmt)).scalars().all())

        if employee_id is not None:
            wallet = await self.get_wallet_by_employee_id(employee_id)
            if not wallet:
                return {
                    "available_points": 0, "total_earned_points": 0,
                    "pts_this_month": 0, "pts_last_month": 0,
                    "rewards_total": 0, "rewards_this_month": 0, "rewards_last_month": 0,
                }

            pts_this, pts_last = 0, 0
            if credit_ids:
                pts_this_stmt = select(func.coalesce(func.sum(PointTransaction.amount), 0)).where(
                    PointTransaction.wallet_id == wallet.wallet_id,
                    PointTransaction.transaction_type_id.in_(credit_ids),
                    PointTransaction.transaction_at >= start_this,
                    PointTransaction.transaction_at < end_this,
                )
                pts_last_stmt = select(func.coalesce(func.sum(PointTransaction.amount), 0)).where(
                    PointTransaction.wallet_id == wallet.wallet_id,
                    PointTransaction.transaction_type_id.in_(credit_ids),
                    PointTransaction.transaction_at >= start_last,
                    PointTransaction.transaction_at < end_last,
                )
                pts_this = int((await self.db.execute(pts_this_stmt)).scalar() or 0)
                pts_last = int((await self.db.execute(pts_last_stmt)).scalar() or 0)

            # Reward redemptions count
            rew_tot_stmt = select(func.count(RewardHistory.history_id)).where(RewardHistory.wallet_id == wallet.wallet_id)
            rew_this_stmt = select(func.count(RewardHistory.history_id)).where(
                RewardHistory.wallet_id == wallet.wallet_id,
                RewardHistory.granted_at >= start_this,
                RewardHistory.granted_at < end_this,
            )
            rew_last_stmt = select(func.count(RewardHistory.history_id)).where(
                RewardHistory.wallet_id == wallet.wallet_id,
                RewardHistory.granted_at >= start_last,
                RewardHistory.granted_at < end_last,
            )

            rewards_total = int((await self.db.execute(rew_tot_stmt)).scalar() or 0)
            rewards_this = int((await self.db.execute(rew_this_stmt)).scalar() or 0)
            rewards_last = int((await self.db.execute(rew_last_stmt)).scalar() or 0)

            return {
                "available_points": wallet.available_points,
                "total_earned_points": wallet.total_earned_points,
                "pts_this_month": pts_this,
                "pts_last_month": pts_last,
                "rewards_total": rewards_total,
                "rewards_this_month": rewards_this,
                "rewards_last_month": rewards_last,
            }

        # Platform-wide stats (when employee_id is None)
        tot_avail_stmt = select(func.coalesce(func.sum(Wallet.available_points), 0))
        tot_earned_stmt = select(func.coalesce(func.sum(Wallet.total_earned_points), 0))
        avail_points = int((await self.db.execute(tot_avail_stmt)).scalar() or 0)
        total_earned = int((await self.db.execute(tot_earned_stmt)).scalar() or 0)

        pts_this, pts_last = 0, 0
        if credit_ids:
            pts_this_stmt = select(func.coalesce(func.sum(PointTransaction.amount), 0)).where(
                PointTransaction.transaction_type_id.in_(credit_ids),
                PointTransaction.transaction_at >= start_this,
                PointTransaction.transaction_at < end_this,
            )
            pts_last_stmt = select(func.coalesce(func.sum(PointTransaction.amount), 0)).where(
                PointTransaction.transaction_type_id.in_(credit_ids),
                PointTransaction.transaction_at >= start_last,
                PointTransaction.transaction_at < end_last,
            )
            pts_this = int((await self.db.execute(pts_this_stmt)).scalar() or 0)
            pts_last = int((await self.db.execute(pts_last_stmt)).scalar() or 0)

        rew_tot_stmt = select(func.count(RewardHistory.history_id))
        rew_this_stmt = select(func.count(RewardHistory.history_id)).where(
            RewardHistory.granted_at >= start_this,
            RewardHistory.granted_at < end_this,
        )
        rew_last_stmt = select(func.count(RewardHistory.history_id)).where(
            RewardHistory.granted_at >= start_last,
            RewardHistory.granted_at < end_last,
        )
        rewards_total = int((await self.db.execute(rew_tot_stmt)).scalar() or 0)
        rewards_this = int((await self.db.execute(rew_this_stmt)).scalar() or 0)
        rewards_last = int((await self.db.execute(rew_last_stmt)).scalar() or 0)

        return {
            "available_points": avail_points,
            "total_earned_points": total_earned,
            "pts_this_month": pts_this,
            "pts_last_month": pts_last,
            "rewards_total": rewards_total,
            "rewards_this_month": rewards_this,
            "rewards_last_month": rewards_last,
        }

    async def get_wallet_stats_batch(self, employee_ids: list[uuid.UUID]) -> dict[str, dict[str, int]]:
        if not employee_ids:
            return {}

        now = datetime.now(timezone.utc)
        start_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_this = start_this + relativedelta(months=1)
        start_last = start_this - relativedelta(months=1)
        end_last = start_this

        zero = {
            "available_points": 0, "total_earned_points": 0,
            "pts_this_month": 0, "pts_last_month": 0,
            "rewards_total": 0, "rewards_this_month": 0, "rewards_last_month": 0,
        }

        # 1. Fetch Wallets
        wallet_stmt = select(Wallet).where(Wallet.employee_id.in_(employee_ids))
        wallets = list((await self.db.execute(wallet_stmt)).scalars().all())
        wallet_map = {w.employee_id: w for w in wallets}
        wallet_ids = [w.wallet_id for w in wallets]

        if not wallet_ids:
            return {str(eid): dict(zero) for eid in employee_ids}

        # 2. Credit transaction types
        credit_ids = list(
            (await self.db.execute(select(TransactionType.type_id).where(TransactionType.is_credit.is_(True)))).scalars().all()
        )

        pts_this_map: dict[uuid.UUID, int] = {}
        pts_last_map: dict[uuid.UUID, int] = {}
        if credit_ids:
            tx_this_stmt = (
                select(PointTransaction.wallet_id, func.sum(PointTransaction.amount))
                .where(
                    PointTransaction.wallet_id.in_(wallet_ids),
                    PointTransaction.transaction_type_id.in_(credit_ids),
                    PointTransaction.transaction_at >= start_this,
                    PointTransaction.transaction_at < end_this,
                )
                .group_by(PointTransaction.wallet_id)
            )
            tx_last_stmt = (
                select(PointTransaction.wallet_id, func.sum(PointTransaction.amount))
                .where(
                    PointTransaction.wallet_id.in_(wallet_ids),
                    PointTransaction.transaction_type_id.in_(credit_ids),
                    PointTransaction.transaction_at >= start_last,
                    PointTransaction.transaction_at < end_last,
                )
                .group_by(PointTransaction.wallet_id)
            )
            pts_this_map = dict((await self.db.execute(tx_this_stmt)).all())
            pts_last_map = dict((await self.db.execute(tx_last_stmt)).all())

        # 3. Reward history counts
        rew_tot_stmt = (
            select(RewardHistory.wallet_id, func.count(RewardHistory.history_id))
            .where(RewardHistory.wallet_id.in_(wallet_ids))
            .group_by(RewardHistory.wallet_id)
        )
        rew_this_stmt = (
            select(RewardHistory.wallet_id, func.count(RewardHistory.history_id))
            .where(
                RewardHistory.wallet_id.in_(wallet_ids),
                RewardHistory.granted_at >= start_this,
                RewardHistory.granted_at < end_this,
            )
            .group_by(RewardHistory.wallet_id)
        )
        rew_last_stmt = (
            select(RewardHistory.wallet_id, func.count(RewardHistory.history_id))
            .where(
                RewardHistory.wallet_id.in_(wallet_ids),
                RewardHistory.granted_at >= start_last,
                RewardHistory.granted_at < end_last,
            )
            .group_by(RewardHistory.wallet_id)
        )

        rew_tot_map = dict((await self.db.execute(rew_tot_stmt)).all())
        rew_this_map = dict((await self.db.execute(rew_this_stmt)).all())
        rew_last_map = dict((await self.db.execute(rew_last_stmt)).all())

        result = {}
        for eid in employee_ids:
            w = wallet_map.get(eid)
            if not w:
                result[str(eid)] = dict(zero)
                continue
            wid = w.wallet_id
            result[str(eid)] = {
                "available_points": w.available_points,
                "total_earned_points": w.total_earned_points,
                "pts_this_month": int(pts_this_map.get(wid, 0)),
                "pts_last_month": int(pts_last_map.get(wid, 0)),
                "rewards_total": int(rew_tot_map.get(wid, 0)),
                "rewards_this_month": int(rew_this_map.get(wid, 0)),
                "rewards_last_month": int(rew_last_map.get(wid, 0)),
            }
        return result

    async def get_leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        stmt = (
            select(Wallet, Employee.username, Department.department_name)
            .outerjoin(Employee, Wallet.employee_id == Employee.employee_id)
            .outerjoin(Department, Employee.department_id == Department.department_id)
            .order_by(Wallet.total_earned_points.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "rank": rank,
                "employee_id": str(w.employee_id),
                "username": uname or "Unknown",
                "department": dname or "N/A",
                "total_earned_points": w.total_earned_points,
            }
            for rank, (w, uname, dname) in enumerate(rows, start=1)
        ]