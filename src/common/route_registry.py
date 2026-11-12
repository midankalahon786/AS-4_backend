"""
src/common/route_registry.py
─────────────────────────────
Auto-registers every route from every microservice into route_permissions
on startup. No manual seeding needed — add a new router endpoint and it
appears in the permissions table automatically.

HOW IT WORKS
────────────
1. Each service calls `register_app_routes(app, default_roles)` in its
   lifespan startup, AFTER DB connects.
2. We walk app.routes, build "METHOD:/path" keys, and upsert them into
   route_permissions for the given default roles.
3. New routes → inserted automatically.
4. Existing active rows → skipped (preserves custom UI assignments).
5. Existing inactive rows → reactivated.
6. Routes removed from code → left in DB as is_active=False.

ROUTE KEY FORMAT
────────────────
Keys are always:  METHOD:/aabhar/v1/<service>/<endpoint>
e.g.             GET:/aabhar/v1/roles/list
                 POST:/aabhar/v1/rewards/redeem

The key is built as:  f"{METHOD}:{root_path}{route.path}"
where root_path = FastAPI(root_path="/v1/roles") — the reverse-proxy prefix.
route.path is the bare path registered on the router, e.g. "/list".

Your ROLE_OVERRIDES and ROUTE_TITLES dicts MUST use this same format.

IMPORTANT — DB UNIQUE CONSTRAINT REQUIRED
──────────────────────────────────────────
route_permissions must have a unique index on (route_key, role_id).
Without it, skip_duplicates=True in create_many is a no-op and you will
get duplicate rows on every restart.

Add to your Prisma schema:
    @@unique([route_key, role_id])

Then run:  prisma migrate dev

USAGE
──────
    from src.common.route_registry import register_app_routes

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.connect()
        await connect_redis()

        await register_app_routes(
            app,
            default_roles=["SUPER_ADMIN", "HR_ADMIN"],
            role_overrides=ROLE_OVERRIDES,
            route_titles=ROUTE_TITLES,
        )
        yield
        ...

ROLE_OVERRIDES — per-route role lists (optional):
    ROLE_OVERRIDES = {
        "GET:/aabhar/v1/dashboard/leaderboard": ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
        "POST:/aabhar/v1/rewards/redeem":       ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    }

ROUTE_TITLES — human-readable labels (optional, auto-generated if absent):
    ROUTE_TITLES = {
        "GET:/aabhar/v1/dashboard/leaderboard": "View Leaderboard",
        "POST:/aabhar/v1/rewards/redeem":       "Redeem Reward",
    }
"""

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.routing import APIRoute

from starlette.routing import Mount, Route

logger = logging.getLogger(__name__)

# ── System routes to always skip ─────────────────────────────────────────────
_SKIP_EXACT: set[str] = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/v1/docs",
    "/v1/redoc",
    "/v1/openapi.json",
}

_SKIP_PREFIXES: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi",
    "/internal",
)

_SYSTEM_ACTOR = None
_REGISTRATION_TIMEOUT_SECONDS = 120


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auto_title(route_key: str) -> str:
    """
    Derive a human-readable title from a route key.

    Examples:
        "GET:/aabhar/v1/rewards/catalog"               → "Get Rewards Catalog"
        "POST:/aabhar/v1/employees/create"             → "Post Employees Create"
        "PATCH:/aabhar/v1/rewards/catalog/{id}/stock"  → "Patch Rewards Catalog Stock"
        "DELETE:/aabhar/v1/orgs/seasonal-multipliers/{id}" → "Delete Orgs Seasonal Multipliers"
    """
    method, _, path = route_key.partition(":")
    parts = path.strip("/").split("/")
    # Drop app prefix and version segments (aabhar, v1, v2 …)
    parts = [p for p in parts if p.lower() != "aabhar" and not re.fullmatch(r"v\d+", p, re.IGNORECASE)]
    # Drop path parameter segments like {employee_id}
    parts = [p for p in parts if not (p.startswith("{") and p.endswith("}"))]
    label = " ".join(p.replace("-", " ") for p in parts).title()
    return f"{method.title()} {label}".strip()


# src/common/route_registry.py

def _extract_routes(
    app: FastAPI,
    always_public_routes: Optional[set[str]] = None,
) -> list[tuple[str, str]]:
    if always_public_routes is None:
        always_public_routes = set()

    root_path = (getattr(app, "root_path", "") or "").rstrip("/")
    seen: set[tuple[str, str]] = set()
    results: list[tuple[str, str]] = []

    def _walk(route_list, prefix=""):
        for r in route_list:
            if isinstance(r, Mount):
                mount_prefix = prefix + (getattr(r, "path", "") or "").rstrip("/")
                sub_routes = getattr(r.app, "routes", getattr(r, "routes", []))
                _walk(sub_routes, prefix=mount_prefix)
                continue

            if hasattr(r, "effective_candidates"):
                cands = r.effective_candidates() if callable(r.effective_candidates) else r.effective_candidates
                _walk(cands, prefix=prefix)
                continue

            if hasattr(r, "routes") and not hasattr(r, "methods"):
                router_prefix = prefix + (getattr(r, "path", "") or "").rstrip("/")
                _walk(r.routes, prefix=router_prefix)
                continue

            if hasattr(r, "original_router") and hasattr(r.original_router, "routes") and not hasattr(r, "methods"):
                inc_prefix = getattr(getattr(r, "include_context", None), "prefix", "") or ""
                _walk(r.original_router.routes, prefix=prefix + inc_prefix.rstrip("/"))
                continue

            route_path = getattr(r, "path", None)
            methods = getattr(r, "methods", None)
            if not route_path or not methods:
                continue

            short_path = prefix + route_path
            full_path = root_path + short_path

            if short_path in _SKIP_EXACT or full_path in _SKIP_EXACT:
                continue
            if any(short_path.startswith(p) for p in _SKIP_PREFIXES):
                continue
            if any(full_path.startswith(p) for p in _SKIP_PREFIXES):
                continue

            for method in sorted(methods):
                method = method.upper()
                if method == "HEAD":
                    continue
                route_key = f"{method}:{full_path}"
                if route_key in always_public_routes:
                    continue
                pair = (method, full_path)
                if pair not in seen:
                    seen.add(pair)
                    results.append(pair)

    _walk(app.routes)
    return results


# ── Core registration logic ───────────────────────────────────────────────────

async def _do_register(
    app: FastAPI,
    default_roles: list[str],
    role_overrides: Optional[dict[str, list[str]]] = None,
    route_titles: Optional[dict[str, str]] = None,
    always_public_routes: Optional[set[str]] = None,
    apply_jitter: bool = True,
) -> None:
    """Inner registration — runs inside an asyncio.wait_for timeout guard."""
    from sqlalchemy import select, update, or_
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.core.database import async_session_factory
    from src.roles.models import Role, RoutePermission

    role_overrides = role_overrides or {}
    route_titles = route_titles or {}
    always_public_routes = always_public_routes or set()

    # Stagger startup so multiple services don't all hit the DB at t=0.
    if apply_jitter:
        jitter = random.uniform(0, 5)
        await asyncio.sleep(jitter)

    async with async_session_factory() as session:
        # ── 1. Load roles ─────────────────────────────────────────────────────────
        res = await session.execute(select(Role))
        all_roles = res.scalars().all()
        role_map: dict[str, Any] = {r.role_code: r.role_id for r in all_roles}

        if not role_map:
            logger.warning("route_registry: no roles in DB — skipping registration")
            return

        now = datetime.now(timezone.utc)

        # ── 1b. Deactivate stale rows for always-public routes ────────────────────
        if always_public_routes:
            await session.execute(
                update(RoutePermission)
                .where(
                    RoutePermission.route_key.in_(list(always_public_routes)),
                    RoutePermission.is_active.is_(True),
                )
                .values(is_active=False, updated_at=now)
            )

        # ── 1c. Deactivate stale rows for internal routes, docs, and health ───────
        await session.execute(
            update(RoutePermission)
            .where(
                or_(
                    RoutePermission.route_key.like("%/internal/%"),
                    RoutePermission.route_key.like("%/docs%"),
                    RoutePermission.route_key.like("%/redoc%"),
                    RoutePermission.route_key.like("%/openapi%"),
                    RoutePermission.route_key.like("%/health%"),
                ),
                RoutePermission.is_active.is_(True),
            )
            .values(is_active=False, updated_at=now)
        )

        # ── 2. Extract routes (deduplicated, always_public + internal excluded) ───
        routes = _extract_routes(app, always_public_routes)
        if not routes:
            logger.warning("route_registry: no routes found in app")
            await session.commit()
            return

        logger.info("route_registry: found %d unique route+method pairs", len(routes))

        # ── 3. Fetch existing rows for these route keys ───────────────────────────
        route_keys = list({f"{method}:{path}" for method, path in routes})
        res_existing = await session.execute(
            select(RoutePermission).where(RoutePermission.route_key.in_(route_keys))
        )
        existing_rows = res_existing.scalars().all()

        existing_active: set[tuple[str, Any]] = set()
        existing_inactive: dict[tuple[str, Any], RoutePermission] = {}

        for row in existing_rows:
            pair = (row.route_key, row.role_id)
            if row.is_active:
                existing_active.add(pair)
            else:
                if pair not in existing_inactive:
                    existing_inactive[pair] = row

        # ── 4. Build insert / reactivate batches ──────────────────────────────────
        to_insert: list[dict] = []
        to_reactivate: list[tuple[RoutePermission, str]] = []
        queued: set[tuple[str, Any]] = set()

        for method, path in routes:
            route_key = f"{method}:{path}"
            roles_for_route = role_overrides.get(route_key, default_roles)
            title = route_titles.get(route_key) or _auto_title(route_key)

            for role_code in roles_for_route:
                role_id = role_map.get(role_code)
                if not role_id:
                    logger.debug(
                        "route_registry: role '%s' not in DB — skipping %s",
                        role_code, route_key,
                    )
                    continue

                pair = (route_key, role_id)
                if pair in existing_active:
                    continue
                elif pair in existing_inactive:
                    if pair not in queued:
                        to_reactivate.append((existing_inactive[pair], title))
                        queued.add(pair)
                else:
                    if pair not in queued:
                        to_insert.append({
                            "route_key": route_key,
                            "title": title,
                            "role_id": role_id,
                            "is_active": True,
                            "created_by": _SYSTEM_ACTOR,
                            "updated_by": _SYSTEM_ACTOR,
                            "updated_at": now,
                        })
                        queued.add(pair)

        # ── 5. Batch insert ───────────────────────────────────────────────────────
        inserted = 0
        if to_insert:
            try:
                stmt = pg_insert(RoutePermission).values(to_insert)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["route_key", "role_id"]
                )
                res_ins = await session.execute(stmt)
                inserted = res_ins.rowcount if res_ins.rowcount is not None and res_ins.rowcount > 0 else len(to_insert)
                logger.debug("route_registry: batch-inserted %d rows", inserted)
            except Exception as err:
                logger.warning("route_registry: batch insert failed: %s", err)

        # ── 6. Reactivate previously-deactivated rows ─────────────────────────────
        reactivated = 0
        errors = 0
        for row, title in to_reactivate:
            try:
                row.is_active = True
                row.title = title
                row.updated_by = _SYSTEM_ACTOR
                row.updated_at = now
                reactivated += 1
            except Exception as err:
                errors += 1
                logger.warning("route_registry: reactivation failed for %s: %s", row.route_key, err)

        await session.commit()

        skipped = len(routes) * len(default_roles) - inserted - reactivated - errors

        # ── 7. Invalidate permissions cache ───────────────────────────────────────
        try:
            from src.common.cache import cache_delete
            await cache_delete("roles:route_permissions")
            logger.debug("route_registry: cache invalidated")
        except Exception as err:
            logger.warning("route_registry: cache invalidation failed: %s", err)

        logger.info(
            "route_registry done — routes=%d | inserted=%d | reactivated=%d | skipped=%d | errors=%d",
            len(routes), inserted, reactivated, skipped, errors,
        )



# ── Public API ────────────────────────────────────────────────────────────────

async def register_app_routes(
    app: FastAPI,
    default_roles: list[str],
    role_overrides: Optional[dict[str, list[str]]] = None,
    route_titles: Optional[dict[str, str]] = None,
    always_public_routes: Optional[set[str]] = None,
    apply_jitter: bool = True,
) -> None:
    """
    Auto-register all routes from `app` into route_permissions.

    Non-fatal — if registration times out or fails, the service still starts.

    Args:
        app:                  The FastAPI app instance for this service.
        default_roles:        Role codes assigned to any route not in role_overrides.
        role_overrides:       {route_key: [role_codes]} for per-route overrides.
        route_titles:         {route_key: "Human Readable Title"}.
                              Routes without an entry get an auto-generated label.
        always_public_routes: Set of route keys (e.g. "POST:/aabhar/v1/auth/login") that
                              are unconditionally public. These are NEVER written to
                              route_permissions and any existing stale rows for them
                              are deactivated. Use this for pre-auth endpoints like
                              login, refresh, forgot-password, validate, etc. that
                              must remain accessible to unauthenticated users and
                              must never be togglable by an admin.
        apply_jitter:         Whether to add random sleep jitter before DB access
                              (default True; set False for deterministic seeding).
    """
    role_overrides        = role_overrides        or {}
    route_titles          = route_titles          or {}
    always_public_routes  = always_public_routes  or set()

    try:
        await asyncio.wait_for(
            _do_register(
                app,
                default_roles,
                role_overrides,
                route_titles,
                always_public_routes,
                apply_jitter=apply_jitter,
            ),
            timeout=_REGISTRATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "route_registry: timed out after %ds — service starting without full "
            "route seeding. Routes will register on next restart.",
            _REGISTRATION_TIMEOUT_SECONDS,
        )
    except Exception as err:
        logger.warning(
            "route_registry: registration failed — service starting without route seeding: %s",
            err,
        )