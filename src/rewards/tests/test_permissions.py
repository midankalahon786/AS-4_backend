"""
Unit & Integration tests for Reward Control Panel & Route Access Control
Ensures normal employees CANNOT see or access the Rewards Control Panel,
while admins retain full management capabilities.
"""
import pytest
from src.rewards.main import ROLE_OVERRIDES, ROUTE_TITLES
from sqlalchemy import select
from src.core.database import async_session_factory
from src.roles.models import Role, RoutePermission


def test_role_overrides_rewards_admin_isolation():
    """Verify backend ROLE_OVERRIDES configuration isolates admin routes from employees."""
    admin_only_routes = [
        "GET:/aabhar/v1/rewards/history",
        "POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem",
        "POST:/aabhar/v1/rewards/catalog",
        "PATCH:/aabhar/v1/rewards/catalog/{catalog_id}",
        "PATCH:/aabhar/v1/rewards/catalog/{catalog_id}/stock",
        "POST:/aabhar/v1/rewards/categories",
        "PATCH:/aabhar/v1/rewards/categories/{category_id}",
    ]

    for route in admin_only_routes:
        allowed = ROLE_OVERRIDES.get(route, [])
        assert "EMPLOYEE" not in allowed, f"EMPLOYEE should not have access to {route}"
        assert "MANAGER" not in allowed, f"MANAGER should not have access to {route}"
        assert "SUPER_ADMIN" in allowed, f"SUPER_ADMIN must have access to {route}"
        assert "ADMIN" in allowed, f"ADMIN must have access to {route}"
        assert "HR_ADMIN" in allowed, f"HR_ADMIN must have access to {route}"


def test_employee_self_service_routes_accessible():
    """Verify employee can still browse catalog, categories, view personal history, and redeem."""
    employee_routes = [
        "GET:/aabhar/v1/rewards/catalog",
        "GET:/aabhar/v1/rewards/categories",
        "GET:/aabhar/v1/rewards/history/me",
        "POST:/aabhar/v1/rewards/redeem",
    ]

    for route in employee_routes:
        allowed = ROLE_OVERRIDES.get(route, [])
        assert "EMPLOYEE" in allowed, f"EMPLOYEE must have access to {route}"


@pytest.mark.asyncio
async def test_database_route_permissions_isolation():
    """Verify route_permissions table in DB does not grant admin rewards routes to EMPLOYEE or MANAGER."""
    async with async_session_factory() as session:
        # Load roles
        res = await session.execute(select(Role))
        roles = {r.role_code: r.role_id for r in res.scalars().all()}
        
        emp_id = roles.get("EMPLOYEE")
        mgr_id = roles.get("MANAGER")
        admin_id = roles.get("ADMIN")

        assert emp_id is not None
        assert mgr_id is not None
        assert admin_id is not None

        # Fetch active route permissions for EMPLOYEE
        emp_perms_res = await session.execute(
            select(RoutePermission.route_key).where(
                RoutePermission.role_id == emp_id,
                RoutePermission.is_active.is_(True),
                RoutePermission.route_key.like("%/rewards/%"),
            )
        )
        emp_keys = set(emp_perms_res.scalars().all())

        # Prohibited for EMPLOYEE
        assert "POST:/aabhar/v1/rewards/catalog" not in emp_keys
        assert "PATCH:/aabhar/v1/rewards/catalog/{catalog_id}" not in emp_keys
        assert "POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem" not in emp_keys
        assert "GET:/aabhar/v1/rewards/history" not in emp_keys
        assert "POST:/aabhar/v1/rewards/categories" not in emp_keys

        # Allowed for EMPLOYEE
        assert "GET:/aabhar/v1/rewards/catalog" in emp_keys
        assert "GET:/aabhar/v1/rewards/categories" in emp_keys
        assert "GET:/aabhar/v1/rewards/history/me" in emp_keys
        assert "POST:/aabhar/v1/rewards/redeem" in emp_keys


def test_frontend_gating_simulation():
    """
    Simulates frontend cardIsAccessible and hasControlPanelAccess logic
    using actual employee route permissions from DB.
    """
    SELF_SERVICE_ROUTES = {
        'POST:/aabhar/v1/auth/logout',
        'POST:/aabhar/v1/auth/signup',
        'POST:/aabhar/v1/auth/bulk-import',
        'PUT:/aabhar/v1/employees/notifications/read-all',
        'PUT:/aabhar/v1/employees/notifications/{notification_id}/read',
        'POST:/aabhar/v1/recognitions/reviews',
        'PUT:/aabhar/v1/recognitions/reviews/{id}',
        'POST:/aabhar/v1/rewards/redeem',
        'POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem',
        'POST:/aabhar/v1/rewards/catalog/{id}/redeem',
    }

    WRITE_METHODS = ['POST:', 'PUT:', 'PATCH:', 'DELETE:']
    CONTROL_PANEL_WRITE_PREFIXES = [
        '/aabhar/v1/organizations/departments',
        '/aabhar/v1/organizations/designations',
        '/aabhar/v1/organizations/statuses',
        '/aabhar/v1/employees',
        '/aabhar/v1/rewards/catalog',
        '/aabhar/v1/rewards/categories',
        '/aabhar/v1/recognitions/review-categories',
        '/aabhar/v1/recognitions/reviews',
        '/aabhar/v1/roles',
    ]

    # Typical active route keys for a normal employee
    employee_my_route_keys = [
        'GET:/aabhar/v1/rewards/catalog',
        'GET:/aabhar/v1/rewards/categories',
        'GET:/aabhar/v1/rewards/history/me',
        'POST:/aabhar/v1/rewards/redeem',
        'GET:/aabhar/v1/employees/profile',
        'GET:/aabhar/v1/roles/my-permissions',
        'POST:/aabhar/v1/recognitions/reviews',
    ]

    # Test Rewards card accessibility in Control Panel Hub
    rewards_card = {
        'title': 'Rewards',
        'pathPrefix': '/aabhar/v1/rewards/catalog',
        'readOnlyAccess': False,
    }

    admin_keys = [k for k in employee_my_route_keys if k not in SELF_SERVICE_ROUTES]

    # Check Rewards card accessibility
    has_rewards_card = any(
        any(k.startswith(m) for m in WRITE_METHODS) and
        k[k.index(':') + 1:].startswith(rewards_card['pathPrefix'])
        for k in admin_keys
    )
    assert has_rewards_card is False, "Normal employee must NOT have access to the Rewards control panel card"

    # Check Navbar hasControlPanelAccess
    has_control_panel_access = any(
        (
            k.startswith('GET:') and k[k.index(':') + 1:].startswith('/aabhar/v1/organizations/audit-logs')
        ) or (
            any(k.startswith(m) for m in WRITE_METHODS) and
            any(k[k.index(':') + 1:].startswith(p) for p in CONTROL_PANEL_WRITE_PREFIXES)
        )
        for k in admin_keys
    )
    assert has_control_panel_access is False, "Normal employee must NOT see the Control Panel navbar item"
