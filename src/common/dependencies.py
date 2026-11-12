"""
src/common/dependencies.py
──────────────────────────
Core authentication and RBAC route-permission dependencies.
Driven by JWT validation, Redis caching, and SQLAlchemy 2.0 async lookups.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.common.cache import L1_MEDIUM, TTL_MEDIUM, cache_delete, cache_get, cache_set
from src.core.database import async_session_factory
from src.core.security import decode_token
from src.roles.models import RoutePermission

security = HTTPBearer(auto_error=False)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL")
_AUTH_CACHE_TTL = 30

_PUBLIC_PATHS: set[str] = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/v1/docs",
    "/v1/redoc",
    "/v1/openapi.json",
}


def register_public_paths(*paths: str) -> None:
    _PUBLIC_PATHS.update(paths)


def _is_public(request: Request) -> bool:
    path = request.scope.get("path") or (request.url.path if "headers" in request.scope else "")
    return path in _PUBLIC_PATHS


def _build_route_key(request: Request) -> str:
    matched_route = request.scope.get("route")
    scope_path = request.scope.get("path") or (request.url.path if "headers" in request.scope else "")
    app = request.scope.get("app")
    root_path = (getattr(app, "root_path", "") or request.scope.get("root_path", "") or "").rstrip("/")

    # If scope_path already starts with root_path, strip it to work with app-relative path
    rel_path = scope_path
    if root_path and rel_path.startswith(root_path):
        rel_path = rel_path[len(root_path):]
    if not rel_path.startswith("/"):
        rel_path = "/" + rel_path

    if isinstance(matched_route, APIRoute):
        bare_path = matched_route.path
        # If the route was included with a prefix (e.g. /dashboard), matched_route.path
        # might be '/leaderboard' while rel_path is '/dashboard/leaderboard'.
        # Preserve the prefix from rel_path.
        if not rel_path.startswith(bare_path) and bare_path in rel_path:
            prefix_end = rel_path.find(bare_path)
            if prefix_end > 0:
                prefix = rel_path[:prefix_end].rstrip("/")
                bare_path = prefix + bare_path
        elif "{" in bare_path and not rel_path.startswith(bare_path):
            bare_parts = bare_path.strip("/").split("/")
            rel_parts = rel_path.strip("/").split("/")
            if len(rel_parts) > len(bare_parts):
                prefix_len = len(rel_parts) - len(bare_parts)
                prefix = "/" + "/".join(rel_parts[:prefix_len])
                bare_path = prefix + bare_path
    else:
        bare_path = rel_path

    if not bare_path.startswith("/"):
        bare_path = "/" + bare_path

    full_path = root_path + bare_path
    return f"{request.method.upper()}:{full_path}"


_auth_client: httpx.AsyncClient | None = None


def get_auth_client() -> httpx.AsyncClient:
    global _auth_client
    if _auth_client is None or _auth_client.is_closed:
        _auth_client = httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=20,
                keepalive_expiry=30,
            ),
        )
    return _auth_client


async def close_auth_client() -> None:
    global _auth_client
    if _auth_client and not _auth_client.is_closed:
        await _auth_client.aclose()
        _auth_client = None


class CurrentUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    email: str | None = ""
    roles: list[str]
    department_id: str | None = None


_PUBLIC_USER = CurrentUser(id="system", email="", roles=["PUBLIC"])


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    if _is_public(request):
        return _PUBLIC_USER

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cache_key = f"auth:token:{token_hash}"

    try:
        cached = await asyncio.wait_for(cache_get(cache_key), timeout=2.0)
        if cached is not None:
            cached_id = cached.get("id")
            if not cached_id or str(cached_id).lower() == "null":
                await cache_delete(cache_key)
            else:
                return CurrentUser.model_validate(cached)
    except Exception:
        pass

    # Remote Auth service check
    if AUTH_SERVICE_URL:
        try:
            client = get_auth_client()
            response = await client.post(
                AUTH_SERVICE_URL,
                json={"token": token},
                headers={"X-Request-ID": request_id},
            )

            if response.status_code == 200 and response.json().get("valid"):
                data = response.json()
                user = CurrentUser(
                    id=str(data["user_id"]),
                    email=data.get("email") or "",
                    roles=[r.upper() for r in data.get("roles", [])],
                    department_id=data.get("department_id"),
                )
                try:
                    await cache_set(cache_key, user.model_dump(), ttl=_AUTH_CACHE_TTL)
                except Exception:
                    pass
                return user
        except httpx.RequestError:
            pass

    # Local fallback verification
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired or is invalid",
        )

    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id or str(user_id).lower() == "null":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: missing user_id",
        )

    return CurrentUser(
        id=str(user_id),
        email=payload.get("email") or "",
        roles=[r.upper() for r in payload.get("roles", [])],
        department_id=payload.get("department_id"),
    )


async def check_route_permission(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if _is_public(request):
        return current_user

    if any(r in current_user.roles for r in ("SUPER_ADMIN", "ADMIN")):
        return current_user

    route_key = _build_route_key(request)
    perm_cache_key = f"roles:route_permissions:{route_key}"
    cached_roles: list[str] | None = await cache_get(perm_cache_key, l1_ttl=L1_MEDIUM)

    if cached_roles is None:
        keys_to_check = [route_key]
        if "/dashboard/" in route_key:
            keys_to_check.append(route_key.replace("/dashboard/", "/"))
        elif "/analytics/" in route_key:
            keys_to_check.append(route_key.replace("/analytics/", "/analytics/dashboard/"))

        async with async_session_factory() as session:
            stmt = (
                select(RoutePermission)
                .options(joinedload(RoutePermission.role))
                .where(
                    RoutePermission.route_key.in_(keys_to_check),
                    RoutePermission.is_active.is_(True),
                )
            )
            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No permissions configured for {route_key}",
                )

            cached_roles = [
                r.role.role_code.upper() for r in rows if r.role and r.role.role_code
            ]
            await cache_set(perm_cache_key, cached_roles, ttl=TTL_MEDIUM, l1_ttl=L1_MEDIUM)

    if not cached_roles or not any(r in set(cached_roles) for r in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for this operation",
        )

    return current_user


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number"),
        size: int = Query(10, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.size = size