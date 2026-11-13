"""
src/wallet/main.py — Wallet Service entry point.
Powered by FastAPI, SQLAlchemy 2.0 Async, Redis, and OpenTelemetry.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

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
from src.wallet.employee_consumer import employee_created_consumer_loop
from src.wallet.internal_router import router as internal_router
from src.wallet.review_consumer import review_created_consumer_loop
from src.wallet.reward_consumer import reward_redeemed_consumer_loop
from src.wallet.router import router as wallet_router

logger = logging.getLogger(__name__)

ROLE_OVERRIDES = {
    "GET:/aabhar/v1/wallets/employees/{employee_id}":       ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/wallets/{wallet_id}/balance":           ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/wallets/{wallet_id}/points-summary":    ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/wallets/transactions":                  ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/wallets/transactions/{transaction_id}": ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/wallets/transactions/types":            ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "POST:/aabhar/v1/wallets/transactions":                 ["SUPER_ADMIN", "HR_ADMIN", "MANAGER"],
}
ROUTE_TITLES = {
    "GET:/aabhar/v1/wallets/employees/{employee_id}":        "Get Employee Wallet",
    "GET:/aabhar/v1/wallets/{wallet_id}/balance":            "Get Wallet Balance",
    "GET:/aabhar/v1/wallets/{wallet_id}/points-summary":     "Get Points Summary",
    "GET:/aabhar/v1/wallets/transactions":                   "List All Transactions",
    "GET:/aabhar/v1/wallets/transactions/{transaction_id}":  "Get Transaction Details",
    "GET:/aabhar/v1/wallets/transactions/types":             "List Transaction Types",
    "POST:/aabhar/v1/wallets/transactions":                  "Create Transaction",
}


async def sqlalchemy_integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    """Handles reference number collisions or duplicate wallet records."""
    return JSONResponse(
        status_code=409,
        content={"detail": "A database constraint was violated. A transaction with this reference number already exists."},
    )


def _make_consumer_task(
    loop_fn,
    shutdown_event: asyncio.Event,
    name: str,
    consumer_tasks: list,
) -> asyncio.Task:
    """
    Create a consumer task with a done-callback that:
    - Logs any unhandled exception so silent crashes are visible[cite: 29]
    - Auto-restarts the consumer after a 3-second delay if it crashes[cite: 29]
    """
    task = asyncio.create_task(loop_fn(shutdown_event), name=name)

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error("Consumer task '%s' crashed: %s — restarting in 3s", name, exc)
            if not shutdown_event.is_set():
                async def _restart():
                    await asyncio.sleep(3)
                    if not shutdown_event.is_set():
                        new_task = _make_consumer_task(loop_fn, shutdown_event, name, consumer_tasks)
                        for i, old in enumerate(consumer_tasks):
                            if old is t:
                                consumer_tasks[i] = new_task
                                break
                        else:
                            consumer_tasks.append(new_task)
                        logger.info("Consumer task '%s' restarted", name)
                asyncio.ensure_future(_restart())
        else:
            if not shutdown_event.is_set():
                logger.warning("Consumer task '%s' exited cleanly without shutdown signal", name)

    task.add_done_callback(_on_done)
    return task


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Connect and verify PostgreSQL via SQLAlchemy
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    print("Wallet Service: 🟢 Database Connected (SQLAlchemy 2.0 Async)")

    _shutdown = asyncio.Event()
    consumer_tasks = []

    # 2. Redis and stream consumers
    try:
        await connect_redis()
        print("Wallet Service: ☑️  Redis Connected")

        consumer_tasks.extend([
            _make_consumer_task(employee_created_consumer_loop, _shutdown, "employee_created_consumer", consumer_tasks),
            _make_consumer_task(review_created_consumer_loop,   _shutdown, "review_created_consumer",   consumer_tasks),
            _make_consumer_task(reward_redeemed_consumer_loop,  _shutdown, "reward_redeemed_consumer",  consumer_tasks),
        ])

        # Yield to the event loop so all consumer tasks start execution
        await asyncio.sleep(0)
        print("Wallet Service: 👂 Stream consumers started")
    except Exception as exc:
        print(f"Wallet Service: ⚠️  Redis unavailable ({exc}) — consumers disabled")

    # 3. Dynamic route registration
    await register_app_routes(
        app,
        default_roles=["SUPER_ADMIN", "HR_ADMIN"],
        role_overrides=ROLE_OVERRIDES,
        route_titles=ROUTE_TITLES,
    )

    yield

    # Clean shutdown
    _shutdown.set()
    for task in consumer_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    print("Wallet Service: 👂 Consumers stopped")

    await close_auth_client()
    await disconnect_redis()
    await engine.dispose()
    print("Wallet Service: 🔴 Database Disconnected & Pool Disposed")


app = FastAPI(
    title="Wallet Service",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

initialize_cors_and_middleware(app)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": "Wallet Service"}


# Deprecated route remains for signal consistency[cite: 29]
@app.post("/credit-from-review", include_in_schema=False)
async def credit_from_review_deprecated():
    return JSONResponse(status_code=410, content={
        "detail": "Deprecated. Use the review.created Redis Stream event instead."
    })


# Middleware & Exception Handlers
app.middleware("http")(request_rate_limit_middleware)
app.add_exception_handler(IntegrityError,         sqlalchemy_integrity_error_handler)
app.add_exception_handler(HTTPException,          http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception,              generic_exception_handler)

# Routers
app.include_router(wallet_router)
app.include_router(internal_router)

# Instrumentation
setup_telemetry(app, "rnr-wallet", excluded_urls="health,docs,openapi.json,redoc,internal")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.wallet.main:app", host="0.0.0.0", port=8006, reload=True)
