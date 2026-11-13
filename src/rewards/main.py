"""
src/rewards/main.py
───────────────────
Reward Service entry point.
Powered by FastAPI, SQLAlchemy 2.0 Async, Redis, and OpenTelemetry.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.common.cors_setup import initialize_cors_and_middleware
from src.common.middleware import (
    generic_exception_handler,
    http_exception_handler,
    request_rate_limit_middleware,
    validation_exception_handler,
)
from src.common.route_registry import register_app_routes
from src.common.telemetry import setup_telemetry
from src.core.database import engine
from src.core.logger import logger
from src.notifications.redis_client import connect_redis, disconnect_redis
from src.rewards.router import router as rewards_router

ROLE_OVERRIDES = {
    "GET:/aabhar/v1/rewards/catalog":                      ["SUPER_ADMIN", "ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/rewards/categories":                   ["SUPER_ADMIN", "ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/rewards/history":                      ["SUPER_ADMIN", "ADMIN", "HR_ADMIN"],
    "GET:/aabhar/v1/rewards/history/me":                   ["SUPER_ADMIN", "ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "POST:/aabhar/v1/rewards/redeem":                      ["SUPER_ADMIN", "ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem": ["SUPER_ADMIN", "ADMIN", "HR_ADMIN"],
    "POST:/aabhar/v1/rewards/catalog":                     ["SUPER_ADMIN", "ADMIN", "HR_ADMIN"],
    "PATCH:/aabhar/v1/rewards/catalog/{catalog_id}":       ["SUPER_ADMIN", "ADMIN", "HR_ADMIN"],
    "PATCH:/aabhar/v1/rewards/catalog/{catalog_id}/stock": ["SUPER_ADMIN", "ADMIN", "HR_ADMIN"],
    "POST:/aabhar/v1/rewards/categories":                  ["SUPER_ADMIN", "ADMIN", "HR_ADMIN"],
    "PATCH:/aabhar/v1/rewards/categories/{category_id}":   ["SUPER_ADMIN", "ADMIN", "HR_ADMIN"],
}

ROUTE_TITLES = {
    "GET:/aabhar/v1/rewards/catalog":                        "Browse Rewards Catalog",
    "GET:/aabhar/v1/rewards/categories":                     "List Reward Categories",
    "GET:/aabhar/v1/rewards/history":                        "View All Redemption History",
    "GET:/aabhar/v1/rewards/history/me":                     "View My Redemption History",
    "POST:/aabhar/v1/rewards/redeem":                        "Redeem Reward",
    "POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem":   "Redeem Reward by ID",
    "POST:/aabhar/v1/rewards/catalog":                       "Add Catalog Item",
    "PATCH:/aabhar/v1/rewards/catalog/{catalog_id}":         "Update Catalog Item",
    "PATCH:/aabhar/v1/rewards/catalog/{catalog_id}/stock":   "Update Catalog Item Stock",
    "POST:/aabhar/v1/rewards/categories":                    "Create Reward Category",
    "PATCH:/aabhar/v1/rewards/categories/{category_id}":     "Update Reward Category",
}


async def sqlalchemy_integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    """Handles category code or SKU unique constraint collisions cleanly."""
    return JSONResponse(
        status_code=409,
        content={"detail": "A database constraint was violated. A reward code or category code already exists."},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Reward Microservice...")
    # 1. Connect and verify PostgreSQL via SQLAlchemy
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Rewards Service: 🟢 Database Connected (SQLAlchemy 2.0 Async)")

    # 2. Redis setup
    try:
        await connect_redis()
        logger.info("Rewards Service: ☑️  Redis Connected")
    except Exception as e:
        logger.warning(
            "Rewards Service: ⚠️  Redis unavailable (%s) — notifications will not be queued in real-time", e
        )

    # 3. Dynamic route registration
    await register_app_routes(
        app,
        default_roles=["SUPER_ADMIN", "ADMIN", "HR_ADMIN"],
        role_overrides=ROLE_OVERRIDES,
        route_titles=ROUTE_TITLES,
    )

    yield

    # Clean shutdown
    logger.info("Shutting down Reward Microservice...")
    await disconnect_redis()
    await engine.dispose()
    logger.info("Rewards Service: 🔴 Database Disconnected & Connection Pool Disposed")


app = FastAPI(
    title="Reward Microservice",
    description="API for managing the reward catalog, categories, and point redemptions.",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

initialize_cors_and_middleware(app)


@app.get("/health", tags=["System"])
async def health_check():
    logger.debug("Health check endpoint pinged.")
    db_status = "Disconnected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "Connected"
    except Exception:
        db_status = "Unavailable"

    return {
        "service": "Reward Microservice",
        "status": "System Operational",
        "version": "1.0.0",
        "database": db_status,
    }


# Middleware & Exception Handlers
app.middleware("http")(request_rate_limit_middleware)
app.add_exception_handler(IntegrityError, sqlalchemy_integrity_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Register Reward Endpoints
app.include_router(rewards_router)

# OpenTelemetry Instrumentation
setup_telemetry(app, "rnr-rewards", excluded_urls="health,/docs,/openapi.json,/redoc")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.rewards.main:app", host="0.0.0.0", port=8006, reload=True)
