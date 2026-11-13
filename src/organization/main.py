"""
src/organization/main.py
────────────────────────
Organization Service entry point.
Handles company structure: Departments, Designations, Department Types, Statuses, and Audits.
Powered by FastAPI, SQLAlchemy 2.0 Async, Redis, and OpenTelemetry.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
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
from src.organization.router import (
    audit_logs_router,
    department_types_router,
    departments_router,
    designations_router,
    statuses_router,
)

# ── Role Overrides ────────────────────────────────────────────────────────────[cite: 18]
ROLE_OVERRIDES: dict[str, list[str]] = {
    # Departments
    "GET:/aabhar/v1/organizations/departments":                            ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/organizations/departments/{department_id}":            ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "POST:/aabhar/v1/organizations/departments":                           ["SUPER_ADMIN", "HR_ADMIN"],
    "PUT:/aabhar/v1/organizations/departments/{department_id}":            ["SUPER_ADMIN", "HR_ADMIN"],
    # Department Types
    "GET:/aabhar/v1/organizations/department-types":                       ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    # Designations
    "GET:/aabhar/v1/organizations/designations":                           ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/organizations/designations/{designation_id}":          ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "POST:/aabhar/v1/organizations/designations":                          ["SUPER_ADMIN", "HR_ADMIN"],
    "PUT:/aabhar/v1/organizations/designations/{designation_id}":          ["SUPER_ADMIN", "HR_ADMIN"],
    # Statuses
    "GET:/aabhar/v1/organizations/statuses":                               ["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"],
    "GET:/aabhar/v1/organizations/statuses/{status_id}":                   ["SUPER_ADMIN", "HR_ADMIN"],
    "POST:/aabhar/v1/organizations/statuses":                              ["SUPER_ADMIN"],
    "PUT:/aabhar/v1/organizations/statuses/{status_id}":                   ["SUPER_ADMIN"],
    # Audit Logs
    "GET:/aabhar/v1/organizations/audit-logs":                             ["SUPER_ADMIN", "HR_ADMIN"],
    "GET:/aabhar/v1/organizations/audit-logs/{audit_id}":                  ["SUPER_ADMIN", "HR_ADMIN"],
}

# ── Route Titles ──────────────────────────────────────────────────────────────[cite: 18]
ROUTE_TITLES: dict[str, str] = {
    # Departments
    "GET:/aabhar/v1/organizations/departments":                            "List Departments",
    "GET:/aabhar/v1/organizations/departments/{department_id}":            "Get Department Details",
    "POST:/aabhar/v1/organizations/departments":                           "Create Department",
    "PUT:/aabhar/v1/organizations/departments/{department_id}":            "Update Department",
    # Department Types
    "GET:/aabhar/v1/organizations/department-types":                       "List Department Types",
    # Designations
    "GET:/aabhar/v1/organizations/designations":                           "List Designations",
    "GET:/aabhar/v1/organizations/designations/{designation_id}":          "Get Designation Details",
    "POST:/aabhar/v1/organizations/designations":                          "Create Designation",
    "PUT:/aabhar/v1/organizations/designations/{designation_id}":          "Update Designation",
    # Statuses
    "GET:/aabhar/v1/organizations/statuses":                               "List Statuses",
    "GET:/aabhar/v1/organizations/statuses/{status_id}":                   "Get Status Details",
    "POST:/aabhar/v1/organizations/statuses":                              "Create Status",
    "PUT:/aabhar/v1/organizations/statuses/{status_id}":                   "Update Status",
    # Audit Logs
    "GET:/aabhar/v1/organizations/audit-logs":                             "List Audit Logs",
    "GET:/aabhar/v1/organizations/audit-logs/{audit_id}":                  "Get Audit Log Details",
}

_PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


async def sqlalchemy_integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    """Handles unique constraints (e.g., department or designation code collisions) cleanly."""
    return JSONResponse(
        status_code=409,
        content={"detail": "A database constraint was violated. A conflicting code or name already exists."},
    )


# ── Lifespan ──────────────────────────────────────────────────────────────────[cite: 18]
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Connect and verify PostgreSQL via SQLAlchemy
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    print("Organization Service: 🟢 Database Connected (SQLAlchemy 2.0 Async)")

    # 2. Redis Cache setup
    try:
        await connect_redis()
        print("Organization Service: ☑️  Redis Connected")
    except Exception as e:
        print(f"Organization Service: ⚠️  Redis unavailable ({e}) — caching disabled")

    # 3. Dynamic route registration
    await register_app_routes(
        app,
        default_roles=["SUPER_ADMIN", "HR_ADMIN"],
        role_overrides=ROLE_OVERRIDES,
        route_titles=ROUTE_TITLES,
    )

    yield

    # Clean up connections on shutdown
    print("Organization Service: Disconnecting...")
    await close_auth_client()
    await disconnect_redis()
    await engine.dispose()
    print("Organization Service: 🔴 Database Disconnected & Pool Disposed")


# ── App ───────────────────────────────────────────────────────────────────────[cite: 18]
app = FastAPI(
    title="Organization Service",
    description="Microservice for handling company structure: Departments, Designations, and Statuses",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    lifespan=lifespan,
)

initialize_cors_and_middleware(app)

app.middleware("http")(request_rate_limit_middleware)

app.add_exception_handler(IntegrityError, sqlalchemy_integrity_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": "Organization Service"}


# Routers
app.include_router(departments_router, prefix="/departments", tags=["Departments"])
app.include_router(designations_router, prefix="/designations", tags=["Designations"])
app.include_router(department_types_router, prefix="/department-types", tags=["Department Types"])
app.include_router(statuses_router, prefix="/statuses", tags=["Status Master"])
app.include_router(audit_logs_router, prefix="/audit-logs", tags=["Audit Logs"])


# ── OpenAPI Schema ────────────────────────────────────────────────────────────[cite: 18]
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {})
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    for path, path_item in schema.get("paths", {}).items():
        if path in _PUBLIC_PATHS:
            continue
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

setup_telemetry(app, "rnr-organization", excluded_urls="health,/docs,/openapi.json")

if __name__ == "__main__":
    uvicorn.run("src.organization.main:app", host="0.0.0.0", port=8007, reload=True)
