"""
src/common/audit.py
───────────────────
Banking-grade audit layer for Aabhar Rewards & Recognition.
Driven by PostgreSQL session settings and SQLAlchemy 2.0 async writes.
"""

from __future__ import annotations

import datetime as _dt
import logging
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Callable, Optional

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"
_SENSITIVE = frozenset({"password_hash", "token_hash", "replaced_by_token"})


async def set_audit_context(
    session: AsyncSession,
    user_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Sets PostgreSQL session variables for database triggers to consume."""
    # Use set_config(name, value, is_local) to bind to current transaction
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": user_id or SYSTEM_USER_ID},
    )
    if ip_address:
        await session.execute(
            text("SELECT set_config('app.current_ip', :ip, true)"),
            {"ip": ip_address},
        )
    if user_agent:
        await session.execute(
            text("SELECT set_config('app.current_user_agent', :ua, true)"),
            {"ua": user_agent[:500]},
        )


@asynccontextmanager
async def audit_ctx(
    *,
    user_id: str,
    table_name: str,
    operation: str,
    record_id: str | Callable[[], str],
    new_values: None | dict | Callable[[], dict | None] = None,
    old_values: None | dict | Callable[[], dict | None] = None,
    request: Request | None = None,
    ip_address: str | None = None,
    session: AsyncSession | None = None,
):
    """
    Context manager that:
      1. Sets PostgreSQL session context for DB triggers.
      2. Yields execution to the calling operation.
      3. Writes an application-level audit row on completion.
    """
    req_ip, user_agent = _extract_request_info(request)
    resolved_ip = req_ip if request is not None else ip_address

    # Step 1: Set PostgreSQL session variables
    if session is not None:
        try:
            await set_audit_context(
                session,
                user_id=user_id,
                ip_address=resolved_ip,
                user_agent=user_agent,
            )
        except Exception as exc:
            logger.error("Failed to set audit context on session: %s", exc)

    # Step 2: Yield to write block
    try:
        yield
    except Exception:
        raise

    # Step 3: Write application-level audit row
    await _write_app_audit(
        table_name=table_name,
        record_id=_resolve(record_id),
        operation=operation,
        performed_by=user_id,
        old_values=_resolve(old_values),
        new_values=_resolve(new_values),
        ip_address=resolved_ip,
        user_agent=user_agent,
    )


async def audit(
    *,
    table_name: str,
    record_id: str,
    operation: str,
    performed_by: str,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Direct standalone application-level audit log entry."""
    ip_address, user_agent = _extract_request_info(request)
    await _write_app_audit(
        table_name=table_name,
        record_id=record_id,
        operation=operation,
        performed_by=performed_by,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def _write_app_audit(
    *,
    table_name: str,
    record_id: str,
    operation: str,
    performed_by: str,
    old_values: Optional[dict],
    new_values: Optional[dict],
    ip_address: Optional[str],
    user_agent: Optional[str],
) -> None:
    insert_sql = text("""
        INSERT INTO audit_log (
            table_name, record_id, operation_type, performed_by,
            ip_address, user_agent, old_values, new_values, performed_at
        ) VALUES (
            :table_name, :record_id, :operation_type, :performed_by,
            :ip_address, :user_agent, 
            CAST(:old_values AS jsonb), 
            CAST(:new_values AS jsonb), 
            NOW()
        )
    """)

    import json

    sanitized_old = json.dumps(_sanitise(old_values))
    sanitized_new = json.dumps(_sanitise(new_values))

    try:
        async with async_session_factory() as session:
            await session.execute(
                insert_sql,
                {
                    "table_name": table_name,
                    "record_id": str(record_id),
                    "operation_type": operation.upper(),
                    "performed_by": str(performed_by),
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "old_values": sanitized_old,
                    "new_values": sanitized_new,
                },
            )
            await session.commit()
    except Exception as exc:
        logger.error(
            "Application audit_log write failed | table=%s record=%s op=%s | %s",
            table_name,
            record_id,
            operation,
            exc,
            exc_info=True,
        )


def _extract_request_info(
    request: Request | None,
) -> tuple[str | None, str | None]:
    ip_address: str | None = None
    user_agent: str | None = None
    if request is not None:
        try:
            forwarded_for = request.headers.get("x-forwarded-for")
            real_ip = request.headers.get("x-real-ip")
            if forwarded_for:
                ip_address = forwarded_for.split(",")[0].strip()
            elif real_ip:
                ip_address = real_ip.strip()
            else:
                ip_address = request.client.host if request.client else None
        except Exception:
            pass
        try:
            user_agent = request.headers.get("user-agent")
        except Exception:
            pass
    return ip_address, user_agent


def _resolve(value: Any) -> Any:
    return value() if callable(value) else value


def _sanitise(values: dict[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}

    def _coerce(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (bool, int, float, str)):
            return v
        if isinstance(v, dict):
            return {k: _coerce(val) for k, val in v.items()}
        if isinstance(v, (list, tuple)):
            return [_coerce(i) for i in v]
        if isinstance(v, uuid.UUID):
            return str(v)
        if isinstance(v, (_dt.datetime, _dt.date)):
            return v.isoformat()
        if isinstance(v, Decimal):
            return float(v)
        return str(v)

    return {k: _coerce(v) for k, v in values.items() if k not in _SENSITIVE}
