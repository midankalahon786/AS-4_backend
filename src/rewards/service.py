"""
src/rewards/service.py
──────────────────────
Reward management and redemption service.
Decoupled via IRewardRepository and PostgreSQL AsyncSession.
"""
from __future__ import annotations

import math
import uuid
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status

from src.common import internal_client
from src.common.audit import audit_ctx
from src.common.cache import (
    L1_MEDIUM,
    L1_PERMANENT,
    L1_VOLATILE,
    TTL_MEDIUM,
    TTL_PERMANENT,
    TTL_VOLATILE,
    cache_get,
    cache_set,
    invalidate_pattern,
)
from src.common.event_publisher import publish
from src.core.logger import logger
from src.notifications.schemas import NotificationType
from src.notifications.service import NotificationService
from src.rewards import schemas
from src.rewards.interfaces import IRewardRepository
from src.rewards.models import RewardCatalog, RewardCategory, RewardHistory


def _key_catalog(active_only: bool, page: int, size: int) -> str:
    return f"rewards:catalog:{int(active_only)}:{page}:{size}"


def _key_categories(is_active: bool | None) -> str:
    flag = "none" if is_active is None else str(int(is_active))
    return f"rewards:categories:{flag}"


def _key_history(wallet_id: UUID | None, page: int, size: int) -> str:
    wid = str(wallet_id) if wallet_id else "all"
    return f"rewards:history:{wid}:{page}:{size}"


def _key_wallet_id(employee_id: UUID) -> str:
    return f"rewards:wallet_id:{employee_id}"


async def invalidate_catalog() -> None:
    await invalidate_pattern("rewards:catalog:*")


async def invalidate_categories() -> None:
    await invalidate_pattern("rewards:categories:*")


async def invalidate_history(wallet_id: UUID | None = None) -> None:
    await invalidate_pattern("rewards:history:all:*")
    if wallet_id:
        await invalidate_pattern(f"rewards:history:{wallet_id}:*")


class RewardService:
    def __init__(self, repo: IRewardRepository, notif_service: NotificationService | None = None):
        self.repo = repo
        self._notif = notif_service

    @staticmethod
    def _get_stock_status(stock: int) -> str:
        if stock <= 0:
            return "Out of Stock"
        if stock < 10:
            return "Limited Stock"
        return "In Stock"

    def _map_catalog_item(self, item: RewardCatalog) -> schemas.RewardItemResponse:
        cat_data = None
        if item.category:
            cat_data = schemas.MinimalCategoryInfo(
                category_id=item.category.category_id,
                category_name=item.category.category_name,
                category_code=item.category.category_code,
            )
        return schemas.RewardItemResponse(
            catalog_id=item.catalog_id,
            reward_name=item.reward_name,
            reward_code=item.reward_code,
            description=item.description,
            default_points=item.default_points,
            min_points=item.min_points,
            max_points=item.max_points,
            is_active=item.is_active,
            created_at=item.created_at,
            category=cat_data,
            stock_status=self._get_stock_status(item.available_stock),
            available_stock=item.available_stock,
        )

    # ── Category Management ───────────────────────────────────────────────────

    async def create_category(
        self,
        request: schemas.CreateCategoryRequest,
        user_id: UUID,
        req_info: Request,
    ) -> schemas.CategoryResponse:
        existing = await self.repo.get_category_by_code(request.category_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category code already exists",
            )

        new_category = None
        async with audit_ctx(
            user_id=str(user_id),
            request=req_info,
            table_name="reward_categories",
            record_id=lambda: str(new_category.category_id) if new_category else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "category_name": request.category_name,
                "category_code": request.category_code,
                "description": request.description,
            },
        ):
            new_category = await self.repo.create_category(request, user_id)

        await invalidate_categories()
        return schemas.CategoryResponse.model_validate(new_category)

    async def get_categories(
        self, is_active: bool | None = None
    ) -> list[schemas.CategoryResponse]:
        key = _key_categories(is_active)
        cached = await cache_get(key, l1_ttl=L1_MEDIUM)
        if cached is not None:
            return [schemas.CategoryResponse(**c) for c in cached]

        result = await self.repo.list_categories(is_active=is_active)
        response = [schemas.CategoryResponse.model_validate(r) for r in result]
        await cache_set(
            key,
            [r.model_dump(mode="json") for r in response],
            ttl=TTL_MEDIUM,
            l1_ttl=L1_MEDIUM,
        )
        return response

    async def update_category(
        self,
        category_id: UUID,
        request: schemas.UpdateCategoryRequest,
        user_id: UUID,
        req_info: Request,
    ) -> schemas.CategoryResponse:
        existing = await self.repo.get_category_by_id(category_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
            )

        update_data = request.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update",
            )

        has_changes = any(getattr(existing, k, None) != v for k, v in update_data.items())
        if not has_changes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The provided values are identical to the current data.",
            )

        old_snapshot = {
            "category_name": existing.category_name,
            "description": existing.description,
            "is_active": existing.is_active,
        }

        updated = None
        async with audit_ctx(
            user_id=str(user_id),
            request=req_info,
            table_name="reward_categories",
            record_id=str(category_id),
            operation="UPDATE",
            old_values=old_snapshot,
            new_values=lambda: update_data,
        ):
            updated = await self.repo.update_category(category_id, update_data, user_id)

        await invalidate_categories()
        return schemas.CategoryResponse.model_validate(updated)

    # ── Catalog Management ────────────────────────────────────────────────────

    async def create_item(
        self,
        item: schemas.CreateRewardRequest,
        user_id: UUID,
        req_info: Request,
    ) -> schemas.RewardItemResponse:
        category = await self.repo.get_category_by_id(item.category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
            )
        if not category.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create a reward item under an inactive category.",
            )

        existing = await self.repo.get_item_by_code(item.reward_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reward code already exists",
            )

        new_item = None
        async with audit_ctx(
            user_id=str(user_id),
            request=req_info,
            table_name="reward_catalog",
            record_id=lambda: str(new_item.catalog_id) if new_item else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "reward_name": item.reward_name,
                "reward_code": item.reward_code,
                "category_id": str(item.category_id),
                "default_points": item.default_points,
            },
        ):
            new_item = await self.repo.create_item(item, user_id)

        await invalidate_catalog()
        return self._map_catalog_item(new_item)

    async def get_catalog(
        self, is_active: bool | None = True, page: int = 1, size: int = 20
    ) -> schemas.PaginatedCatalogResponse:
        flag = "all" if is_active is None else str(int(is_active))
        key = f"rewards:catalog:{flag}:{page}:{size}"
        cached = await cache_get(key, l1_ttl=L1_MEDIUM)
        if cached is not None:
            return schemas.PaginatedCatalogResponse(**cached)

        items, total_items = await self.repo.list_catalog(is_active, page, size)
        mapped = [self._map_catalog_item(i) for i in items]
        total_pages = math.ceil(total_items / size) if total_items else 0

        res = schemas.PaginatedCatalogResponse(
            data=mapped,
            pagination=schemas.PaginationMeta(
                current_page=page,
                per_page=size,
                total=total_items,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )
        await cache_set(key, res.model_dump(mode="json"), ttl=TTL_MEDIUM, l1_ttl=L1_MEDIUM)
        return res

    async def add_stock(
        self,
        catalog_id: UUID,
        request: schemas.AddStockRequest,
        user_id: UUID,
        req_info: Request,
    ) -> schemas.RewardItemResponse:
        item = await self.repo.get_item_by_id(catalog_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reward item not found"
            )

        old_stock = item.available_stock
        updated_item = None
        async with audit_ctx(
            user_id=str(user_id),
            request=req_info,
            table_name="reward_catalog",
            record_id=str(catalog_id),
            operation="RESTOCK",
            old_values={"available_stock": old_stock},
            new_values=lambda: {
                "available_stock": updated_item.available_stock if updated_item else old_stock + request.amount,
                "added": request.amount,
            },
        ):
            updated_item, _ = await self.repo.add_stock(catalog_id, request.amount, user_id)

        await invalidate_catalog()
        return self._map_catalog_item(updated_item)  # type: ignore

    async def update_item(
        self,
        catalog_id: UUID,
        request: schemas.UpdateRewardRequest,
        user_id: UUID,
        req_info: Request,
    ) -> schemas.RewardItemResponse:
        existing_item = await self.repo.get_item_by_id(catalog_id)
        if not existing_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reward item not found"
            )

        new_min = request.min_points if request.min_points is not None else existing_item.min_points
        new_max = request.max_points if request.max_points is not None else existing_item.max_points
        new_default = request.default_points if request.default_points is not None else existing_item.default_points

        if new_min > new_max:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Min points ({new_min}) cannot be greater than Max points ({new_max})",
            )
        if not (new_min <= new_default <= new_max):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Default points ({new_default}) must be between {new_min} and {new_max}",
            )

        update_data = request.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update",
            )

        if "category_id" in update_data and update_data["category_id"]:
            new_category = await self.repo.get_category_by_id(update_data["category_id"])
            if not new_category:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="The specified target category was not found.",
                )
            if not new_category.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move a reward item to an inactive category.",
                )

        if update_data.get("is_active") is True:
            target_cat_id = update_data.get("category_id", existing_item.category_id)
            cat = await self.repo.get_category_by_id(target_cat_id)
            if cat and not cat.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot reactivate this reward because its parent category is inactive.",
                )

        old_snapshot = {
            "reward_name": existing_item.reward_name,
            "default_points": existing_item.default_points,
            "min_points": existing_item.min_points,
            "max_points": existing_item.max_points,
            "is_active": existing_item.is_active,
        }

        updated_item = None
        async with audit_ctx(
            user_id=str(user_id),
            request=req_info,
            table_name="reward_catalog",
            record_id=str(catalog_id),
            operation="UPDATE",
            old_values=old_snapshot,
            new_values=lambda: {
                k: str(v) if isinstance(v, uuid.UUID) else v
                for k, v in update_data.items()
            },
        ):
            updated_item = await self.repo.update_item(catalog_id, update_data, user_id)

        await invalidate_catalog()
        return self._map_catalog_item(updated_item)  # type: ignore

    # ── Redemption ────────────────────────────────────────────────────────────

    async def grant_reward(
        self,
        wallet_id: UUID,
        request: schemas.RedeemRewardRequest | schemas.RedeemRewardRequestOptionalCatalog,
        granted_by_user_id: UUID,
        req_info: Request | None = None,
    ) -> schemas.RedemptionResponse:
        logger.info(
            "Initiating grant_reward | catalog=%s wallet=%s",
            request.catalog_id,
            wallet_id,
        )

        reward_item = await self.repo.get_item_by_id(request.catalog_id)
        if not reward_item or not reward_item.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reward is invalid or inactive",
            )
        if reward_item.available_stock <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Out of stock!"
            )

        points_to_deduct = (
            request.points if request.points is not None else reward_item.default_points
        )
        if not (reward_item.min_points <= points_to_deduct <= reward_item.max_points):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Points are outside the allowed range",
            )

        wallet_data = None
        try:
            wallet_data = await internal_client.get_wallet_by_id(str(wallet_id))
        except Exception as exc:
            logger.warning("Could not fetch wallet %s via internal client: %s", wallet_id, exc)

        if not wallet_data:
            wallet = await self.repo.get_wallet_by_id(wallet_id)
            if not wallet:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
                )
            wallet_data = {
                "wallet_id": str(wallet.wallet_id),
                "employee_id": str(wallet.employee_id),
                "available_points": wallet.available_points,
            }

        available_points = wallet_data.get("available_points", 0)
        if available_points < points_to_deduct:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance",
            )

        try:
            async with audit_ctx(
                user_id=str(granted_by_user_id),
                request=req_info,
                table_name="reward_history",
                record_id=lambda: str(history_record.history_id) if history_record else "UNKNOWN",
                operation="REDEEM",
                new_values=lambda: {
                    "wallet_id": str(wallet_id),
                    "catalog_id": str(request.catalog_id),
                    "points": points_to_deduct,
                    "granted_by": str(granted_by_user_id),
                },
            ):
                updated_catalog, history_record = await self.repo.claim_reward_atomic(
                    catalog_id=request.catalog_id,
                    wallet_id=wallet_id,
                    points=points_to_deduct,
                    granted_by_user_id=granted_by_user_id,
                    comment=request.comment,
                )
        except ValueError as val_err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
        except Exception as e:
            logger.error("grant_reward DB write failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Transaction failed: {str(e)}",
            )

        client_ip = req_info.client.host if req_info and req_info.client else ""

        # Publish event for the Wallet consumer to deduct points asynchronously
        await publish("events:reward.redeemed", {
            "history_id": str(history_record.history_id),
            "wallet_id": str(wallet_id),
            "points": str(points_to_deduct),
            "catalog_id": str(request.catalog_id),
            "redeemed_by": str(granted_by_user_id),
            "ip_address": client_ip,
        })

        await invalidate_catalog()
        await invalidate_history(wallet_id)

        if self._notif:
            try:
                employee_id = wallet_data.get("employee_id")
                if employee_id:
                    await self._notif.create_notification(
                        employee_id=employee_id,
                        title=f'You redeemed "{reward_item.reward_name}"',
                        message=(
                            f"{points_to_deduct} points were used to redeem "
                            f'"{reward_item.reward_name}".'
                            + (f" Note: {request.comment}" if request.comment else "")
                        ),
                        type=NotificationType.REWARD,
                    )
            except Exception:
                logger.exception("Redemption notification failed — redemption succeeded")

        return schemas.RedemptionResponse(
            history_id=history_record.history_id,
            points=history_record.points,
            granted_at=history_record.granted_at,
            status="COMPLETED",
            new_stock_level=updated_catalog.available_stock,
            new_balance=available_points - points_to_deduct,
        )

    # ── History ───────────────────────────────────────────────────────────────

    async def get_history(
        self, wallet_id: UUID | None = None, page: int = 1, size: int = 10
    ) -> schemas.PaginatedHistoryResponse:
        if wallet_id:
            wallet_found = False
            try:
                await internal_client.get_wallet_by_id(str(wallet_id))
                wallet_found = True
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
            except Exception:
                pass

            if not wallet_found:
                db_wallet = await self.repo.get_wallet_by_id(wallet_id)
                if not db_wallet:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found."
                    )

        key = _key_history(wallet_id, page, size)
        cached = await cache_get(key, l1_ttl=L1_VOLATILE)
        if cached is not None:
            return schemas.PaginatedHistoryResponse(**cached)

        history_records, total_items = await self.repo.list_history(wallet_id, page, size)

        mapped_records = []
        for h in history_records:
            cat_info = None
            if h.catalog_item:
                cat_info = schemas.MinimalCatalogInfo(
                    reward_name=h.catalog_item.reward_name,
                    reward_code=h.catalog_item.reward_code,
                )
            emp_info = None
            if h.granted_by_employee:
                emp_info = schemas.MinimalEmployeeInfo(
                    username=h.granted_by_employee.username,
                    email=h.granted_by_employee.email,
                )
            mapped_records.append(
                schemas.RewardHistoryResponse(
                    history_id=h.history_id,
                    points=h.points,
                    comment=h.comment,
                    granted_at=h.granted_at,
                    reward_catalog=cat_info,
                    granted_by=emp_info,
                )
            )

        response = schemas.PaginatedHistoryResponse(
            data=mapped_records,
            total_items=total_items,
            page=page,
            size=size,
        )
        await cache_set(key, response.model_dump(mode="json"), ttl=TTL_VOLATILE, l1_ttl=L1_VOLATILE)
        return response

    async def get_wallet_id_for_user(self, employee_id: UUID) -> UUID | None:
        key = _key_wallet_id(employee_id)
        cached = await cache_get(key, l1_ttl=L1_PERMANENT)
        if cached is not None:
            return UUID(cached)
        try:
            data = await internal_client.get_wallet_by_employee(str(employee_id))
            wid_str = data.get("wallet_id")
            if wid_str:
                wid = UUID(wid_str)
                await cache_set(key, str(wid), ttl=TTL_PERMANENT, l1_ttl=L1_PERMANENT)
                return wid
        except Exception as exc:
            logger.warning("Could not fetch wallet via internal client for employee %s: %s", employee_id, exc)

        # Fallback to direct DB query
        try:
            wallet = await self.repo.get_wallet_by_employee_id(employee_id)
            if wallet:
                await cache_set(key, str(wallet.wallet_id), ttl=TTL_PERMANENT, l1_ttl=L1_PERMANENT)
                return wallet.wallet_id
        except Exception as exc:
            logger.error("Could not fetch wallet via DB fallback for employee %s: %s", employee_id, exc)

        return None