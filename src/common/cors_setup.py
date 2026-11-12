"""
src/common/cors_setup.py
────────────────────────
CORS gatekeeper for ALB/CloudFront and global exception wiring.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError

from src.common.middleware import (
    generic_exception_handler,
    http_exception_handler,
    request_rate_limit_middleware,
    sqlalchemy_integrity_handler,
    validation_exception_handler,
)


def initialize_cors_and_middleware(app: FastAPI) -> None:
    """Handles CORS for AWS ALB and attaches rate-limiting and global exception handlers."""
    origins_raw = os.getenv("FRONTEND_CORS_ORIGINS", "https://aabhar.top,http://localhost:3000")
    origins = [o.strip() for o in origins_raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.middleware("http")(request_rate_limit_middleware)

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(IntegrityError, sqlalchemy_integrity_handler)
    app.add_exception_handler(Exception, generic_exception_handler)