"""
src/rewards/router.py
─────────────────────
API routes for reward categories, catalog, stock management, and redemptions.
Powered by RewardService with SQLAlchemy 2.0 async session dependency injection.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.common.dependencies import CurrentUser, PaginationParams, check_route_permission
from src.core.logger import logger
from src.rewards import schemas
from src.rewards.dependencies import get_reward_service
from src.rewards.service import RewardService

COMMON_ERRORS = {
    401: {"model": schemas.ErrorResponse, "description": "Bearer token missing or expired"},
    403: {"model": schemas.ErrorResponse, "description": "Insufficient permissions"},
    500: {"model": schemas.ErrorResponse, "description": "Internal server configuration error"},
}

router = APIRouter(
    tags=["Rewards"],
    responses=COMMON_ERRORS,
)


# ══════════════════════════════════════════════════════════════
#  CATEGORY ENDPOINTS
# ══════════════════════════════════════════════════════════════

@router.post(
    "/categories",
    response_model=schemas.CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Reward Category",
)
async def create_category(
    request: Request,
    body: schemas.CreateCategoryRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    """Create a new reward category."""
    user_id = UUID(str(current_user.id))
    logger.info("User %s requested to create category: %s", user_id, body.category_name)
    return await service.create_category(body, user_id=user_id, req_info=request)


@router.patch(
    "/categories/{category_id}",
    response_model=schemas.CategoryResponse,
    summary="Update Reward Category",
)
async def update_category(
    category_id: UUID,
    request: Request,
    body: schemas.UpdateCategoryRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    """Update a category."""
    user_id = UUID(str(current_user.id))
    logger.info("User %s updating category: %s", user_id, category_id)
    return await service.update_category(
        category_id=category_id,
        request=body,
        user_id=user_id,
        req_info=request,
    )


@router.get(
    "/categories",
    response_model=list[schemas.CategoryResponse],
    summary="List Reward Categories",
)
async def get_categories(
    is_active: bool | None = None,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    """Fetch categories with optional active status filter."""
    logger.debug("User %s fetching categories. is_active: %s", current_user.id, is_active)
    return await service.get_categories(is_active=is_active)


# ══════════════════════════════════════════════════════════════
#  CATALOG ENDPOINTS
# ══════════════════════════════════════════════════════════════

@router.post(
    "/catalog",
    response_model=schemas.RewardItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Catalog Item",
)
async def create_reward_item(
    request: Request,
    item: schemas.CreateRewardRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    user_id = UUID(str(current_user.id))
    logger.info("Admin %s creating reward item: %s", user_id, item.reward_code)
    return await service.create_item(item, user_id=user_id, req_info=request)


@router.patch(
    "/catalog/{catalog_id}",
    response_model=schemas.RewardItemResponse,
    summary="Update Catalog Item",
)
async def update_reward_item(
    catalog_id: UUID,
    request: Request,
    body: schemas.UpdateRewardRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    user_id = UUID(str(current_user.id))
    logger.info("Admin %s updating catalog item: %s", user_id, catalog_id)
    return await service.update_item(
        catalog_id=catalog_id,
        request=body,
        user_id=user_id,
        req_info=request,
    )


@router.get(
    "/catalog",
    response_model=schemas.PaginatedCatalogResponse,
    summary="View Reward Catalog",
)
async def view_catalog(
    is_active: bool | None = Query(None, description="True=Active, False=Archived, Null=All"),
    pagination: PaginationParams = Depends(),
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    """View the catalog with pagination and nested category details."""
    logger.debug("User %s viewing catalog page %s", current_user.id, pagination.page)
    return await service.get_catalog(
        is_active=is_active,
        page=pagination.page,
        size=pagination.size,
    )


@router.patch(
    "/catalog/{catalog_id}/stock",
    response_model=schemas.RewardItemResponse,
    summary="Add Stock",
)
async def restock_item(
    catalog_id: UUID,
    body: schemas.AddStockRequest,
    request: Request,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    """Adds stock to an existing reward item."""
    user_id = UUID(str(current_user.id))
    logger.info("User %s restocking item %s with %d units", user_id, catalog_id, body.amount)
    return await service.add_stock(
        catalog_id=catalog_id,
        request=body,
        user_id=user_id,
        req_info=request,
    )


# ══════════════════════════════════════════════════════════════
#  REDEMPTION ENDPOINTS
# ══════════════════════════════════════════════════════════════

@router.post(
    "/redeem",
    response_model=schemas.RedemptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Redeem Reward Item",
)
async def redeem_reward(
    request: Request,
    body: schemas.RedeemRewardRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    user_id = UUID(str(current_user.id))
    logger.info("User %s attempting to redeem catalog item %s", user_id, body.catalog_id)

    wallet_id = await service.get_wallet_id_for_user(user_id)
    if not wallet_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found for the authenticated user.",
        )

    return await service.grant_reward(
        wallet_id=wallet_id,
        request=body,
        granted_by_user_id=user_id,
        req_info=request,
    )


@router.post(
    "/catalog/{catalog_id}/redeem",
    response_model=schemas.RedemptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Redeem Reward Item by Catalog ID",
)
async def redeem_reward_by_catalog_id(
    catalog_id: UUID,
    request: Request,
    body: schemas.RedeemRewardRequestOptionalCatalog | None = None,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    user_id = UUID(str(current_user.id))
    logger.info("User %s attempting to redeem catalog item %s", user_id, catalog_id)

    wallet_id = await service.get_wallet_id_for_user(user_id)
    if not wallet_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found for the authenticated user.",
        )

    redeem_req = schemas.RedeemRewardRequest(
        catalog_id=catalog_id,
        points=body.points if body else None,
        comment=body.comment if body else None,
    )

    return await service.grant_reward(
        wallet_id=wallet_id,
        request=redeem_req,
        granted_by_user_id=user_id,
        req_info=request,
    )


# ══════════════════════════════════════════════════════════════
#  REWARD HISTORY ENDPOINTS
# ══════════════════════════════════════════════════════════════

@router.get(
    "/history/me",
    response_model=schemas.PaginatedHistoryResponse,
    summary="My Reward History",
)
async def get_my_history(
    pagination: PaginationParams = Depends(),
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    user_id = UUID(str(current_user.id))
    my_wallet_id = await service.get_wallet_id_for_user(user_id)

    if not my_wallet_id:
        return schemas.PaginatedHistoryResponse(
            data=[],
            total_items=0,
            page=pagination.page,
            size=pagination.size,
        )

    return await service.get_history(
        wallet_id=my_wallet_id,
        page=pagination.page,
        size=pagination.size,
    )


@router.get(
    "/history",
    response_model=schemas.PaginatedHistoryResponse,
    summary="Global Reward History (Admin View)",
)
async def get_all_history(
    wallet_id: UUID | None = None,
    pagination: PaginationParams = Depends(),
    current_user: CurrentUser = Depends(check_route_permission),
    service: RewardService = Depends(get_reward_service),
):
    """Admin View: View history for all users or filter by a specific wallet."""
    logger.info("Admin %s fetching global reward history.", current_user.id)
    return await service.get_history(
        wallet_id=wallet_id,
        page=pagination.page,
        size=pagination.size,
    )