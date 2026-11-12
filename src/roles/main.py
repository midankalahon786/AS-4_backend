"""
src/roles/main.py
─────────────────
Roles & Permissions Service entry point.
Powered by FastAPI, SQLAlchemy 2.0 Async, Redis, and OpenTelemetry.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.common.cors_setup import initialize_cors_and_middleware
from src.common.dependencies import close_auth_client
from src.common.middleware import (
    generic_exception_handler,
    http_exception_handler,
    request_rate_limit_middleware,
    validation_exception_handler,
)
from src.common.route_registry import register_app_routes
from src.common.telemetry import setup_telemetry
from src.core.database import engine
from src.notifications.redis_client import connect_redis, disconnect_redis
from src.roles.router import router

# ── Route Configuration ───────────────────────────────────────────────────────
ROLE_OVERRIDES: dict[str, list[str]] = {
    # ── Roles ─────────────────────────────────────────────────────────────────
    "GET:/aabhar/v1/roles/list":                           ["SUPER_ADMIN", "HR_ADMIN"],
    "POST:/aabhar/v1/roles/create":                        ["SUPER_ADMIN"],

    # ── Employee ↔ Role ───────────────────────────────────────────────────────
    "GET:/aabhar/v1/roles/employees":                      ["SUPER_ADMIN", "HR_ADMIN"],
    "POST:/aabhar/v1/roles/assign":                        ["SUPER_ADMIN"],
    "POST:/aabhar/v1/roles/revoke":                        ["SUPER_ADMIN"],

    # ── Route Permissions ─────────────────────────────────────────────────────
    "GET:/aabhar/v1/roles/route-permissions":              ["SUPER_ADMIN"],
    "POST:/aabhar/v1/roles/route-permissions":             ["SUPER_ADMIN"],
    "PATCH:/aabhar/v1/roles/route-permissions":            ["SUPER_ADMIN"],
    "PATCH:/aabhar/v1/roles/route-permissions/title":      ["SUPER_ADMIN"],
    "GET:/aabhar/v1/roles/my-permissions":                 ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
}

ROUTE_TITLES: dict[str, str] = {
    "GET:/aabhar/v1/roles/list":                           "List Roles",
    "POST:/aabhar/v1/roles/create":                        "Create Role",
    "GET:/aabhar/v1/roles/employees":                      "List Employee Role Assignments",
    "POST:/aabhar/v1/roles/assign":                        "Assign Role to Employee",
    "POST:/aabhar/v1/roles/revoke":                        "Revoke Role from Employee",
    "GET:/aabhar/v1/roles/route-permissions":              "List Route Permissions",
    "POST:/aabhar/v1/roles/route-permissions":             "Add Route Permission",
    "PATCH:/aabhar/v1/roles/route-permissions":            "Remove Route Permission",
    "PATCH:/aabhar/v1/roles/route-permissions/title":      "Update Route Display Title",
    "GET:/aabhar/v1/roles/my-permissions":                 "Get My Permissions",
}


async def sqlalchemy_integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    """Handles role code or permission duplicate collisions cleanly."""
    return JSONResponse(
        status_code=409,
        content={"detail": "A database constraint was violated. A role or permission record already exists."},
    )


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Connect and verify PostgreSQL via SQLAlchemy
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    print("Roles Service: 🟢 Database Connected (SQLAlchemy 2.0 Async)")

    # 2. Redis setup
    try:
        await connect_redis()
        print("Roles Service: ☑️  Redis Connected")
    except Exception as e:
        print(f"Roles Service: ⚠️  Redis unavailable ({e})")

    # 3. Dynamic route permissions registration
    await register_app_routes(
        app,
        default_roles=["SUPER_ADMIN"],
        role_overrides=ROLE_OVERRIDES,
        route_titles=ROUTE_TITLES,
    )

    yield

    # Clean shutdown
    print("Roles Service: Disconnecting Redis...")
    await disconnect_redis()
    await close_auth_client()

    print("Roles Service: Disconnecting Database...")
    await engine.dispose()
    print("Roles Service: 🔴 Database Disconnected & Pool Disposed")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Roles & Permissions Service",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/aabhar/v1/roles",
    openapi_url="/openapi.json",
    docs_url="/docs",
)

initialize_cors_and_middleware(app)

app.middleware("http")(request_rate_limit_middleware)
app.add_exception_handler(IntegrityError, sqlalchemy_integrity_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.include_router(router)


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "Roles Service"}


setup_telemetry(app, "rnr-roles", excluded_urls="health,/docs,/openapi.json")

if __name__ == "__main__":
    uvicorn.run("src.roles.main:app", host="0.0.0.0", port=8002, reload=True)