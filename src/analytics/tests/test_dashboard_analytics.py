import uuid
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import Request

from src.analytics.schemas import (
    LeaderboardEntry,
    PlatformStats,
    RecentReview,
    TeamSummary,
)
from src.analytics.service import AnalyticsService
from src.common.dependencies import CurrentUser, _build_route_key


from fastapi.routing import APIRoute

def test_build_route_key_with_dashboard_prefix():
    # Verify _build_route_key maintains /dashboard prefix
    scope = {
        "type": "http",
        "method": "GET",
        "root_path": "/aabhar/v1/analytics",
        "path": "/dashboard/recent-reviews",
        "headers": [],
    }
    mock_route = MagicMock(spec=APIRoute)
    mock_route.path = "/recent-reviews"
    scope["route"] = mock_route
    req = Request(scope)

    key = _build_route_key(req)
    assert key == "GET:/aabhar/v1/analytics/dashboard/recent-reviews"


def test_build_route_key_without_prefix():
    scope = {
        "type": "http",
        "method": "GET",
        "root_path": "/aabhar/v1/analytics",
        "path": "/recent-reviews",
        "headers": [],
    }
    mock_route = MagicMock(spec=APIRoute)
    mock_route.path = "/recent-reviews"
    scope["route"] = mock_route
    req = Request(scope)

    key = _build_route_key(req)
    assert key == "GET:/aabhar/v1/analytics/recent-reviews"


@pytest.mark.asyncio
async def test_analytics_service_recent_reviews_admin_and_employee():
    provider = AsyncMock()
    emp_id = str(uuid.uuid4())
    rev_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Mock provider return
    provider.get_recent_reviews.return_value = [
        {
            "review_id": rev_id,
            "reviewer_name": "alice",
            "category_tags": [{"category_code": "INNOVATION"}],
            "comment": "Great innovation!",
            "review_at": now,
        }
    ]

    service = AnalyticsService(provider=provider, repo=None)

    # 1. Admin call (platform-wide: employee_id is None)
    admin_reviews = await service.get_recent_reviews_list(None)
    assert len(admin_reviews) == 1
    assert admin_reviews[0].reviewer_name == "alice"
    assert "INNOVATION" in admin_reviews[0].tags
    provider.get_recent_reviews.assert_called_with(None, limit=5)

    # 2. Employee call (personal: employee_id provided)
    emp_reviews = await service.get_recent_reviews_list(emp_id)
    assert len(emp_reviews) == 1
    assert emp_reviews[0].review_id == rev_id
    provider.get_recent_reviews.assert_called_with(emp_id, limit=5)


@pytest.mark.asyncio
async def test_analytics_service_platform_stats():
    provider = AsyncMock()
    emp_id = str(uuid.uuid4())

    provider.get_wallet_stats.return_value = {
        "total_earned_points": 5000,
        "pts_this_month": 500,
        "pts_last_month": 300,
        "rewards_total": 10,
        "rewards_this_month": 2,
        "rewards_last_month": 1,
    }
    provider.get_review_stats.return_value = {
        "reviews_total": 8,
        "reviews_this_month": 3,
        "reviews_last_month": 2,
    }
    provider.get_active_users_count.return_value = {
        "now": 25,
        "last_month": 20,
    }

    service = AnalyticsService(provider=provider, repo=None)

    # Admin platform-wide
    stats = await service.get_platform_stats(employee_id=None, is_admin=True)
    assert isinstance(stats, PlatformStats)
    assert stats.total_points.value == 5000
    assert stats.rewards_redeemed.value == 10
    assert stats.reviews_received.value == 8
    assert stats.active_users.value == 25
    provider.get_wallet_stats.assert_called_with(None)
    provider.get_review_stats.assert_called_with(None)

    # Employee personal
    stats_emp = await service.get_platform_stats(employee_id=emp_id, is_admin=False)
    assert stats_emp.total_points.value == 5000
    provider.get_wallet_stats.assert_called_with(emp_id)
    provider.get_review_stats.assert_called_with(emp_id)


@pytest.mark.asyncio
async def test_analytics_service_leaderboard():
    provider = AsyncMock()
    emp_id = uuid.uuid4()
    provider.get_leaderboard_data.return_value = [
        {
            "rank": 1,
            "employee_id": emp_id,
            "username": "champion",
            "department": "Engineering",
            "total_earned_points": 12000,
        }
    ]

    service = AnalyticsService(provider=provider, repo=None)
    lb = await service.get_leaderboard_list()
    assert len(lb) == 1
    assert lb[0].rank == 1
    assert lb[0].username == "champion"
    assert lb[0].total_earned_points == 12000


@pytest.mark.asyncio
async def test_check_route_permission_admin_bypass():
    from src.common.dependencies import check_route_permission

    req = MagicMock(spec=Request)
    req.scope = {
        "type": "http",
        "method": "GET",
        "path": "/dashboard/recent-reviews",
        "headers": [],
    }
    mock_route = MagicMock(spec=APIRoute)
    mock_route.path = "/recent-reviews"
    req.scope["route"] = mock_route

    # Test SUPER_ADMIN bypass
    admin_user = CurrentUser(
        id=str(uuid.uuid4()),
        email="superadmin@example.com",
        roles=["SUPER_ADMIN"],
    )
    res = await check_route_permission(req, current_user=admin_user)
    assert res == admin_user

    # Test ADMIN bypass
    admin_user2 = CurrentUser(
        id=str(uuid.uuid4()),
        email="admin@example.com",
        roles=["ADMIN"],
    )
    res2 = await check_route_permission(req, current_user=admin_user2)
    assert res2 == admin_user2
