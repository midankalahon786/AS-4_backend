"""
src/analytics/main.py
──────────────────────
Analytics Service entrypoint.
Uses SQLAlchemy 2.0 AsyncEngine and Redis for event consumption and caching.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.analytics.reward_consumer import reward_redeemed_consumer_loop
from src.analytics.router import router as analytics_router
from src.common import internal_client
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

ALL_ROLES = ["SUPER_ADMIN", "ADMIN", "HR_ADMIN", "HR_MANAGER", "MANAGER", "EMPLOYEE"]
ADMIN_ROLES = ["SUPER_ADMIN", "ADMIN", "HR_ADMIN", "HR_MANAGER"]

ROLE_OVERRIDES = {
    # Dashboard prefixed routes
    "GET:/aabhar/v1/analytics/dashboard/leaderboard":           ALL_ROLES,
    "GET:/aabhar/v1/analytics/dashboard/recent-reviews":        ALL_ROLES,
    "GET:/aabhar/v1/analytics/dashboard/platform-stats":        ALL_ROLES,
    "GET:/aabhar/v1/analytics/dashboard/teams":                 ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/dashboard/teams/{department_id}": ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/dashboard/participation":         ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/dashboard/recognition-trend":     ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/dashboard/recognition/teams":     ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/dashboard/recognition/users":     ADMIN_ROLES,
    "POST:/aabhar/v1/analytics/dashboard/audit-logs":           ["SUPER_ADMIN", "ADMIN"],
    "GET:/aabhar/v1/analytics/dashboard/audit-logs/{table_name}/{record_id}": ["SUPER_ADMIN", "ADMIN"],
    "GET:/aabhar/v1/analytics/dashboard/notifications/{employee_id}":          ALL_ROLES,
    "PATCH:/aabhar/v1/analytics/dashboard/notifications/{notification_id}/read": ALL_ROLES,

    # Root alias routes (direct paths)
    "GET:/aabhar/v1/analytics/leaderboard":                     ALL_ROLES,
    "GET:/aabhar/v1/analytics/recent-reviews":                  ALL_ROLES,
    "GET:/aabhar/v1/analytics/platform-stats":                  ALL_ROLES,
    "GET:/aabhar/v1/analytics/teams":                           ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/teams/{department_id}":           ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/participation":                   ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/recognition-trend":               ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/recognition/teams":               ADMIN_ROLES,
    "GET:/aabhar/v1/analytics/recognition/users":               ADMIN_ROLES,
    "POST:/aabhar/v1/analytics/audit-logs":                     ["SUPER_ADMIN", "ADMIN"],
    "GET:/aabhar/v1/analytics/audit-logs/{table_name}/{record_id}": ["SUPER_ADMIN", "ADMIN"],
    "GET:/aabhar/v1/analytics/notifications/{employee_id}":     ALL_ROLES,
    "PATCH:/aabhar/v1/analytics/notifications/{notification_id}/read": ALL_ROLES,
}

ROUTE_TITLES = {
    "GET:/aabhar/v1/analytics/dashboard/leaderboard":           "View Leaderboard",
    "GET:/aabhar/v1/analytics/dashboard/recent-reviews":        "View Recent Reviews",
    "GET:/aabhar/v1/analytics/dashboard/platform-stats":        "View Platform Statistics",
    "GET:/aabhar/v1/analytics/dashboard/teams":                 "View All Teams Overview",
    "GET:/aabhar/v1/analytics/dashboard/teams/{department_id}": "View Team Details",
    "GET:/aabhar/v1/analytics/dashboard/participation":         "View Participation Stats",
    "GET:/aabhar/v1/analytics/dashboard/recognition-trend":     "View Recognition Trends",
    "GET:/aabhar/v1/analytics/dashboard/recognition/teams":     "View Team Recognition",
    "GET:/aabhar/v1/analytics/dashboard/recognition/users":     "View User Recognition",
    "POST:/aabhar/v1/analytics/dashboard/audit-logs":           "Record Audit Entry",
    "GET:/aabhar/v1/analytics/dashboard/audit-logs/{table_name}/{record_id}": "View Record History",
    "GET:/aabhar/v1/analytics/dashboard/notifications/{employee_id}": "View Employee Notifications",
    "PATCH:/aabhar/v1/analytics/dashboard/notifications/{notification_id}/read": "Mark Notification Read",

    "GET:/aabhar/v1/analytics/leaderboard":                     "View Leaderboard",
    "GET:/aabhar/v1/analytics/recent-reviews":                  "View Recent Reviews",
    "GET:/aabhar/v1/analytics/platform-stats":                  "View Platform Statistics",
    "GET:/aabhar/v1/analytics/teams":                           "View All Teams Overview",
    "GET:/aabhar/v1/analytics/teams/{department_id}":           "View Team Details",
    "GET:/aabhar/v1/analytics/participation":                   "View Participation Stats",
    "GET:/aabhar/v1/analytics/recognition-trend":               "View Recognition Trends",
    "GET:/aabhar/v1/analytics/recognition/teams":               "View Team Recognition",
    "GET:/aabhar/v1/analytics/recognition/users":               "View User Recognition",
    "POST:/aabhar/v1/analytics/audit-logs":                     "Record Audit Entry",
    "GET:/aabhar/v1/analytics/audit-logs/{table_name}/{record_id}": "View Record History",
    "GET:/aabhar/v1/analytics/notifications/{employee_id}":     "View Employee Notifications",
    "PATCH:/aabhar/v1/analytics/notifications/{notification_id}/read": "Mark Notification Read",
}


async def sqlalchemy_integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    """Handles unique constraint or foreign key violations cleanly."""
    return JSONResponse(
        status_code=409,
        content={"detail": "Database integrity constraint violated. A conflicting record already exists."},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Verify PostgreSQL connection via SQLAlchemy
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    print("Analytics Service: 🟢 Database Connected (SQLAlchemy 2.0 Async)")

    shutdown_event = asyncio.Event()
    consumer_task = None

    # 2. Redis and Background Worker
    try:
        await connect_redis()
        print("Analytics Service: ☑️  Redis Connected")
        consumer_task = asyncio.create_task(
            reward_redeemed_consumer_loop(shutdown_event)
        )
    except Exception as exc:
        print(f"Analytics Service: ⚠️  Redis unavailable ({exc}) — caching disabled")

    # 3. Dynamic Route Registry
    await register_app_routes(
        app,
        default_roles=["SUPER_ADMIN", "HR_ADMIN"],
        role_overrides=ROLE_OVERRIDES,
        route_titles=ROUTE_TITLES,
    )

    yield

    # Cleanup on application shutdown
    shutdown_event.set()
    if consumer_task:
        await consumer_task

    await internal_client.close()
    await close_auth_client()
    await disconnect_redis()
    await engine.dispose()
    print("Analytics Service: 🔴 Disconnected & Connection Pool Disposed")


app = FastAPI(
    title="Analytics Service",
    description="Dashboard analytics and event tracking powered by SQLAlchemy 2.0 and Redis",
    version="1.0.0",
    root_path="/aabhar/v1/analytics",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

initialize_cors_and_middleware(app)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": "Analytics Service"}


# Middleware & Exception Handlers
app.middleware("http")(request_rate_limit_middleware)
app.add_exception_handler(Exception, generic_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(IntegrityError, sqlalchemy_integrity_error_handler)

# Include Dashboard & Analytics Endpoints (both prefixed and root)
app.include_router(analytics_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(analytics_router, tags=["Analytics"])

# OpenTelemetry Instrumentation
setup_telemetry(app, "rnr-analytics", excluded_urls="health,/docs,/openapi.json,/redoc")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.analytics.main:app", host="0.0.0.0", port=8008, reload=True)