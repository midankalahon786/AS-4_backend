"""
src/recognition/main.py  — Recognition Service entry point.
Powered by FastAPI, SQLAlchemy 2.0 Async, Redis, and OpenTelemetry.
"""
from __future__ import annotations

import asyncio
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
from src.core.database import async_session_factory, engine
from src.digest.router import router as digest_router
from src.digest.worker import digest_worker_loop
from src.notifications.email_sender import EmailSender, SMTPConfig
from src.notifications.redis_client import connect_redis, disconnect_redis
from src.recognition.internal_router import router as internal_router
from src.recognition.router import categories_router as review_categories_router
from src.recognition.router import router as recognition_router

ROLE_OVERRIDES = {
    "GET:/aabhar/v1/recognitions/reviews":                    ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/recognitions/reviews/{id}":               ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "POST:/aabhar/v1/recognitions/reviews":                   ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "PUT:/aabhar/v1/recognitions/reviews/{id}":               ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/recognitions/review-categories":          ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "POST:/aabhar/v1/recognitions/review-categories":         ["SUPER_ADMIN", "HR_ADMIN"],
    "PUT:/aabhar/v1/recognitions/review-categories/{id}":     ["SUPER_ADMIN", "HR_ADMIN"],
    "GET:/aabhar/v1/recognitions/digest":                     ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "POST:/aabhar/v1/recognitions/digest/send":               ["SUPER_ADMIN", "HR_ADMIN"],
}
ROUTE_TITLES = {
    "GET:/aabhar/v1/recognitions/reviews":                    "List Reviews",
    "GET:/aabhar/v1/recognitions/reviews/{id}":               "Get Review Details",
    "POST:/aabhar/v1/recognitions/reviews":                   "Submit Review",
    "PUT:/aabhar/v1/recognitions/reviews/{id}":               "Update Review",
    "GET:/aabhar/v1/recognitions/review-categories":          "List Review Categories",
    "POST:/aabhar/v1/recognitions/review-categories":         "Create Review Category",
    "PUT:/aabhar/v1/recognitions/review-categories/{id}":     "Update Review Category",
    "GET:/aabhar/v1/recognitions/digest":                     "View Recognition Digest",
    "POST:/aabhar/v1/recognitions/digest/send":               "Send Recognition Digest",
}


async def sqlalchemy_integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    """Handles category code or unique constraint collisions."""
    return JSONResponse(
        status_code=409,
        content={"detail": "A database constraint was violated. Category code or name already exists."},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Connect and verify PostgreSQL via SQLAlchemy
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    print("Recognition Service: 🟢 Database Connected (SQLAlchemy 2.0 Async)")

    # 2. Redis Connection
    try:
        await connect_redis()
        print("Recognition Service: ☑️  Redis Connected")
    except Exception as exc:
        print(f"Recognition Service: ⚠️  Redis unavailable ({exc})")

    # 3. Background Digest Worker
    sender = EmailSender(SMTPConfig.from_env())
    digest_task = asyncio.create_task(
        digest_worker_loop(async_session_factory, sender),
        name="digest_worker",
    )

    # 4. Route Permissions Registration
    await register_app_routes(
        app,
        default_roles=["SUPER_ADMIN", "HR_ADMIN"],
        role_overrides=ROLE_OVERRIDES,
        route_titles=ROUTE_TITLES,
    )

    yield

    # Clean shutdown
    digest_task.cancel()
    try:
        await digest_task
    except asyncio.CancelledError:
        pass

    await close_auth_client()
    await disconnect_redis()
    await engine.dispose()
    print("Recognition Service: 🔴 Database Disconnected & Pool Disposed")


app = FastAPI(
    title="Recognition Service",
    version="1.0.0",
    root_path="/aabhar/v1/recognitions",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

initialize_cors_and_middleware(app)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": "Recognition Service"}


# Middleware & Exception Handlers
app.middleware("http")(request_rate_limit_middleware)
app.add_exception_handler(IntegrityError,         sqlalchemy_integrity_error_handler)
app.add_exception_handler(HTTPException,          http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception,              generic_exception_handler)

# Routers
app.include_router(recognition_router)
app.include_router(review_categories_router)
app.include_router(digest_router)
app.include_router(internal_router)

# Instrumentation
setup_telemetry(app, "rnr-recognition", excluded_urls="health,docs,openapi.json,redoc,internal")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.recognition.main:app", host="0.0.0.0", port=8005, reload=True)