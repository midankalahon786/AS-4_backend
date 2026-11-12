from contextlib import asynccontextmanager
import sys
import uuid
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, APIRouter
from fastapi.routing import APIRoute

from src.common.route_registry import (
    register_app_routes,
    _auto_title,
    _extract_routes,
    _do_register,
)
import src.common.cache as cache_module

REG = "src.common.route_registry"


@pytest.fixture
def mock_app():
    app = FastAPI(root_path="/aabhar/v1/analytics")
    router = APIRouter()

    @router.get("/leaderboard")
    def leaderboard(): pass

    @router.post("/redeem")
    def redeem(): pass

    app.include_router(router)
    return app


class TestRouteRegistry:

    def test_auto_title(self):
        assert _auto_title("GET:/aabhar/v1/rewards/catalog")   == "Get Rewards Catalog"
        assert _auto_title("POST:/aabhar/v1/employees/create") == "Post Employees Create"

    def test_extract_routes(self, mock_app):
        routes = _extract_routes(mock_app)
        assert len(routes) == 2
        assert ("GET", "/aabhar/v1/analytics/leaderboard") in routes
        assert ("POST", "/aabhar/v1/analytics/redeem") in routes

    # ===========================================================================
    # CORE REGISTRATION LOGIC
    # ===========================================================================

    @pytest.mark.asyncio
    @patch(f"{REG}.asyncio.sleep", AsyncMock())
    async def test_do_register_new_routes(self, mock_app):
        role_id = uuid.uuid4()
        mock_role = MagicMock(role_code="ADMIN", role_id=role_id)

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        # Execute call results:
        # 1. select(Role)
        # 2. update(RoutePermission) stale
        # 3. select(RoutePermission) existing
        # 4. insert(RoutePermission)
        res_roles = MagicMock()
        res_roles.scalars.return_value.all.return_value = [mock_role]

        res_existing = MagicMock()
        res_existing.scalars.return_value.all.return_value = []

        res_insert = MagicMock()
        res_insert.rowcount = 2

        mock_session.execute = AsyncMock(side_effect=[
            res_roles,
            MagicMock(),
            res_existing,
            res_insert,
        ])

        with patch("src.core.database.async_session_factory", return_value=mock_session), \
             patch.object(cache_module, "cache_delete", AsyncMock()):

            await _do_register(mock_app, ["ADMIN"], {}, {}, apply_jitter=False)

            assert mock_session.execute.call_count >= 3
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{REG}.asyncio.sleep", AsyncMock())
    async def test_do_register_reactivate_inactive(self, mock_app):
        role_id = uuid.uuid4()
        mock_role = MagicMock(role_code="ADMIN", role_id=role_id)

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        mock_inactive = MagicMock(
            route_key="GET:/aabhar/v1/analytics/leaderboard",
            role_id=role_id,
            is_active=False,
            id=uuid.uuid4(),
        )

        res_roles = MagicMock()
        res_roles.scalars.return_value.all.return_value = [mock_role]

        res_existing = MagicMock()
        res_existing.scalars.return_value.all.return_value = [mock_inactive]

        res_insert = MagicMock()
        res_insert.rowcount = 1

        mock_session.execute = AsyncMock(side_effect=[
            res_roles,
            MagicMock(),
            res_existing,
            res_insert,
        ])

        with patch("src.core.database.async_session_factory", return_value=mock_session), \
             patch.object(cache_module, "cache_delete", AsyncMock()):

            await _do_register(mock_app, ["ADMIN"], {}, {}, apply_jitter=False)

            assert mock_inactive.is_active is True
            mock_session.commit.assert_called_once()

    # ===========================================================================
    # PUBLIC API & TIMEOUTS
    # ===========================================================================

    @pytest.mark.asyncio
    @patch(f"{REG}._do_register", AsyncMock())
    async def test_register_app_routes_success(self, mock_app):
        await register_app_routes(mock_app, ["ADMIN"])

    @pytest.mark.asyncio
    @patch(f"{REG}._do_register", AsyncMock(side_effect=asyncio.TimeoutError))
    @patch(f"{REG}.logger")
    async def test_register_app_routes_timeout(self, mock_logger, mock_app):
        await register_app_routes(mock_app, ["ADMIN"])
        mock_logger.warning.assert_called()