"""
src/rewards/tests/test_redemption.py
───────────────────────────────────
Comprehensive test suite verifying reward catalog redemption functionality.
"""
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport

from src.rewards import schemas
from src.rewards.service import RewardService
from src.rewards.models import RewardCatalog, RewardHistory
from src.rewards.main import app
from src.common.dependencies import check_route_permission, CurrentUser


@pytest.mark.asyncio
async def test_grant_reward_success():
    repo = AsyncMock()
    service = RewardService(repo=repo)

    catalog_id = uuid.uuid4()
    wallet_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_item = MagicMock(spec=RewardCatalog)
    mock_item.catalog_id = catalog_id
    mock_item.reward_name = "Amazon Gift Card Rs500"
    mock_item.is_active = True
    mock_item.available_stock = 10
    mock_item.min_points = 400
    mock_item.max_points = 600
    mock_item.default_points = 500

    repo.get_item_by_id.return_value = mock_item

    mock_updated_item = MagicMock(spec=RewardCatalog)
    mock_updated_item.available_stock = 9

    mock_history = MagicMock(spec=RewardHistory)
    mock_history.history_id = uuid.uuid4()
    mock_history.points = 500
    mock_history.granted_at = datetime.now(timezone.utc)

    repo.claim_reward_atomic.return_value = (mock_updated_item, mock_history)

    req = schemas.RedeemRewardRequest(catalog_id=catalog_id, points=500, comment="Enjoy")

    with patch("src.rewards.service.internal_client.get_wallet_by_id", new_callable=AsyncMock) as mock_get_wallet:
        mock_get_wallet.return_value = {"wallet_id": str(wallet_id), "available_points": 1000, "employee_id": str(user_id)}
        with patch("src.rewards.service.publish", new_callable=AsyncMock) as mock_pub:
            res = await service.grant_reward(
                wallet_id=wallet_id,
                request=req,
                granted_by_user_id=user_id,
            )

            assert res.status == "COMPLETED"
            assert res.points == 500
            assert res.new_stock_level == 9
            assert res.new_balance == 500
            mock_pub.assert_called_once()


@pytest.mark.asyncio
async def test_grant_reward_default_points_when_omitted():
    repo = AsyncMock()
    service = RewardService(repo=repo)

    catalog_id = uuid.uuid4()
    wallet_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_item = MagicMock(spec=RewardCatalog)
    mock_item.catalog_id = catalog_id
    mock_item.reward_name = "Amazon Gift Card Rs500"
    mock_item.is_active = True
    mock_item.available_stock = 10
    mock_item.min_points = 400
    mock_item.max_points = 600
    mock_item.default_points = 500

    repo.get_item_by_id.return_value = mock_item

    mock_updated_item = MagicMock(spec=RewardCatalog)
    mock_updated_item.available_stock = 9

    mock_history = MagicMock(spec=RewardHistory)
    mock_history.history_id = uuid.uuid4()
    mock_history.points = 500
    mock_history.granted_at = datetime.now(timezone.utc)

    repo.claim_reward_atomic.return_value = (mock_updated_item, mock_history)

    # points is None
    req = schemas.RedeemRewardRequest(catalog_id=catalog_id, points=None, comment=None)

    with patch("src.rewards.service.internal_client.get_wallet_by_id", new_callable=AsyncMock) as mock_get_wallet:
        mock_get_wallet.return_value = {"wallet_id": str(wallet_id), "available_points": 2000, "employee_id": str(user_id)}
        with patch("src.rewards.service.publish", new_callable=AsyncMock):
            res = await service.grant_reward(
                wallet_id=wallet_id,
                request=req,
                granted_by_user_id=user_id,
            )

            assert res.points == 500
            assert res.new_stock_level == 9
            assert res.new_balance == 1500


@pytest.mark.asyncio
async def test_grant_reward_insufficient_points():
    repo = AsyncMock()
    service = RewardService(repo=repo)

    catalog_id = uuid.uuid4()
    wallet_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_item = MagicMock(spec=RewardCatalog)
    mock_item.catalog_id = catalog_id
    mock_item.is_active = True
    mock_item.available_stock = 10
    mock_item.min_points = 400
    mock_item.max_points = 600
    mock_item.default_points = 500
    repo.get_item_by_id.return_value = mock_item

    req = schemas.RedeemRewardRequest(catalog_id=catalog_id, points=500)

    with patch("src.rewards.service.internal_client.get_wallet_by_id", new_callable=AsyncMock) as mock_get_wallet:
        mock_get_wallet.return_value = {"wallet_id": str(wallet_id), "available_points": 200}
        with pytest.raises(HTTPException) as exc_info:
            await service.grant_reward(
                wallet_id=wallet_id,
                request=req,
                granted_by_user_id=user_id,
            )
        assert exc_info.value.status_code == 400
        assert "Insufficient wallet balance" in exc_info.value.detail


@pytest.mark.asyncio
async def test_grant_reward_out_of_stock():
    repo = AsyncMock()
    service = RewardService(repo=repo)

    catalog_id = uuid.uuid4()
    wallet_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_item = MagicMock(spec=RewardCatalog)
    mock_item.catalog_id = catalog_id
    mock_item.is_active = True
    mock_item.available_stock = 0
    mock_item.min_points = 400
    mock_item.max_points = 600
    mock_item.default_points = 500
    repo.get_item_by_id.return_value = mock_item

    req = schemas.RedeemRewardRequest(catalog_id=catalog_id, points=500)

    with pytest.raises(HTTPException) as exc_info:
        await service.grant_reward(
            wallet_id=wallet_id,
            request=req,
            granted_by_user_id=user_id,
        )
    assert exc_info.value.status_code == 400
    assert "Out of stock" in exc_info.value.detail


@pytest.mark.asyncio
async def test_grant_reward_points_outside_range():
    repo = AsyncMock()
    service = RewardService(repo=repo)

    catalog_id = uuid.uuid4()
    wallet_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_item = MagicMock(spec=RewardCatalog)
    mock_item.catalog_id = catalog_id
    mock_item.is_active = True
    mock_item.available_stock = 10
    mock_item.min_points = 400
    mock_item.max_points = 600
    mock_item.default_points = 500
    repo.get_item_by_id.return_value = mock_item

    req = schemas.RedeemRewardRequest(catalog_id=catalog_id, points=700)

    with pytest.raises(HTTPException) as exc_info:
        await service.grant_reward(
            wallet_id=wallet_id,
            request=req,
            granted_by_user_id=user_id,
        )
    assert exc_info.value.status_code == 400
    assert "Points are outside the allowed range" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_wallet_id_fallback_to_db():
    repo = AsyncMock()
    service = RewardService(repo=repo)

    user_id = uuid.uuid4()
    wallet_id = uuid.uuid4()

    mock_wallet = MagicMock()
    mock_wallet.wallet_id = wallet_id
    repo.get_wallet_by_employee_id.return_value = mock_wallet

    with patch("src.rewards.service.internal_client.get_wallet_by_employee", side_effect=Exception("Connection refused")):
        wid = await service.get_wallet_id_for_user(user_id)
        assert wid == wallet_id
        repo.get_wallet_by_employee_id.assert_called_once_with(user_id)


@pytest.mark.asyncio
async def test_api_redeem_endpoints_with_auth():
    catalog_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    wallet_id = uuid.uuid4()

    mock_user = CurrentUser(
        id=user_id,
        email="employee@example.com",
        roles=["EMPLOYEE"],
        department_id=None,
    )

    app.dependency_overrides[check_route_permission] = lambda: mock_user

    mock_response = schemas.RedemptionResponse(
        history_id=uuid.uuid4(),
        points=500,
        granted_at=datetime.now(timezone.utc),
        status="COMPLETED",
        new_stock_level=95,
        new_balance=4500,
    )

    with patch.object(RewardService, "get_wallet_id_for_user", new_callable=AsyncMock) as mock_get_wid, \
         patch.object(RewardService, "grant_reward", new_callable=AsyncMock) as mock_grant:

        mock_get_wid.return_value = wallet_id
        mock_grant.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. POST /redeem
            res1 = await client.post("/redeem", json={"catalog_id": catalog_id, "points": 500})
            assert res1.status_code == 201
            assert res1.json()["status"] == "COMPLETED"
            assert res1.json()["points"] == 500

            # 2. POST /catalog/{catalog_id}/redeem
            res2 = await client.post(f"/catalog/{catalog_id}/redeem", json={"points": 500})
            assert res2.status_code == 201
            assert res2.json()["status"] == "COMPLETED"

    app.dependency_overrides.clear()
