import asyncio
import redis.asyncio as aioredis
from datetime import datetime, timezone
from sqlalchemy import select, update, delete
from src.core.database import async_session_factory
from src.roles.models import Role, RoutePermission
from src.rewards.main import ROLE_OVERRIDES, ROUTE_TITLES, app
from src.common.route_registry import register_app_routes

async def fix_permissions():
    print("Fixing rewards route permissions in database...")
    async with async_session_factory() as session:
        # 1. Fetch roles
        res = await session.execute(select(Role))
        roles = {r.role_code: r.role_id for r in res.scalars().all()}
        print(f"Loaded roles: {list(roles.keys())}")

        now = datetime.now(timezone.utc)

        # 2. Deactivate/delete bad permissions:
        # - EMPLOYEE and MANAGER on GET:/aabhar/v1/rewards/history
        # - EMPLOYEE and MANAGER on POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem
        stale_roles = [roles["EMPLOYEE"], roles["MANAGER"]]
        stale_routes = [
            "GET:/aabhar/v1/rewards/history",
            "POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem"
        ]

        stmt = (
            update(RoutePermission)
            .where(
                RoutePermission.role_id.in_(stale_roles),
                RoutePermission.route_key.in_(stale_routes),
            )
            .values(is_active=False, updated_at=now)
        )
        res_del = await session.execute(stmt)
        print(f"Deactivated {res_del.rowcount} stale permissions for EMPLOYEE & MANAGER.")

        # 3. Ensure ADMIN has all required admin permissions
        admin_id = roles.get("ADMIN")
        if admin_id:
            for route_key, allowed_roles in ROLE_OVERRIDES.items():
                if "ADMIN" in allowed_roles:
                    # check if row exists
                    check_stmt = select(RoutePermission).where(
                        RoutePermission.role_id == admin_id,
                        RoutePermission.route_key == route_key
                    )
                    existing = (await session.execute(check_stmt)).scalars().first()
                    title = ROUTE_TITLES.get(route_key, route_key)
                    if existing:
                        existing.is_active = True
                        existing.title = title
                        existing.updated_at = now
                    else:
                        new_perm = RoutePermission(
                            role_id=admin_id,
                            route_key=route_key,
                            title=title,
                            is_active=True,
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(new_perm)
            print("Ensured ADMIN role has rewards routes.")

        await session.commit()

    # 4. Invalidate Redis caches
    try:
        r = aioredis.from_url("redis://localhost:6379", decode_responses=True)
        keys = await r.keys("roles:route_permissions:*")
        if keys:
            await r.delete(*keys)
            print(f"Flushed {len(keys)} Redis cache keys for route permissions.")
        await r.close()
    except Exception as e:
        print(f"Redis cache flush warning: {e}")

    print("Permissions fix complete.")

if __name__ == "__main__":
    asyncio.run(fix_permissions())
