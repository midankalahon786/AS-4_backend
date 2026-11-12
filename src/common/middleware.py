"""
src/common/middleware.py
────────────────────────
Global exception handlers, rate limiting, and request context middleware.
Zero Prisma dependencies.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

# ── In-Memory Token Bucket / Rate Limiter (Dev & Pod-local) ───────────────────
_RATE_LIMIT = 300  # requests per minute per IP
_WINDOW = 60.0     # seconds
_requests: dict[str, list[float]] = defaultdict(list)


async def request_rate_limit_middleware(
    request: Request, call_next: Callable[[Request], Response]
) -> Response:
    client_ip = request.headers.get("x-forwarded-for") or (
        request.client.host if request.client else "127.0.0.1"
    )
    client_ip = client_ip.split(",")[0].strip()

    now = time.time()
    timestamps = [t for t in _requests[client_ip] if now - t < _WINDOW]
    timestamps.append(now)
    _requests[client_ip] = timestamps

    if len(timestamps) > _RATE_LIMIT:
        logger.warning("Rate limit exceeded for IP %s", client_ip)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many requests. Please slow down."},
        )

    return await call_next(request)


# ── Exception Handlers ────────────────────────────────────────────────────────

async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


async def sqlalchemy_integrity_handler(
    _: Request, exc: IntegrityError
) -> JSONResponse:
    """
    Catches unique constraint, check constraint, or foreign key violations.
    Replaces Prisma's UniqueViolationError handler.
    """
    logger.warning("Database integrity violation: %s", exc.orig)
    detail_msg = "Database conflict: duplicate entry or invalid reference."
    orig_str = str(exc.orig).lower()
    if "unique" in orig_str:
        detail_msg = "A record with this identifier or unique attribute already exists."
    elif "foreign key" in orig_str:
        detail_msg = "The referenced foreign record does not exist."

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": detail_msg},
    )


async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."},
    )