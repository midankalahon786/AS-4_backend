"""
src/auth/service.py
───────────────────
Auth service handling domain logic, token lifecycle, audits, and event emission.
Loosely coupled via IAuthRepository.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

from src.auth.interfaces import IAuthRepository
from src.auth.schemas import EmployeeResponse, SignUpRequest, TokenResponse, TokenValidationResponse
from src.common.audit import audit, audit_ctx
from src.common.event_publisher import publish
from src.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_reset_token,
    decode_reset_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)

try:
    from src.core.email_utils import (
        send_password_reset_confirmation,
        send_password_reset_email,
        send_welcome_email,
    )
    _email_available = True
except Exception:
    _email_available = False
    def send_password_reset_email(*a, **kw) -> bool: return False
    def send_password_reset_confirmation(*a, **kw) -> bool: return False
    def send_welcome_email(*a, **kw) -> bool: return False

logger = logging.getLogger(__name__)

_TOKEN_SEP = "||"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuthService:
    def __init__(self, repo: IAuthRepository) -> None:
        self.repo = repo

    def _build_login_response(
        self, user, access_token: str, refresh_token_raw: str
    ) -> TokenResponse:
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token_raw,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            employee=EmployeeResponse.model_validate(user),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Token Validation
    # ─────────────────────────────────────────────────────────────────────────

    async def validate_token(self, token: str) -> TokenValidationResponse:
        payload = decode_token(token)
        if not payload:
            return TokenValidationResponse(valid=False, error="Invalid or expired token")

        return TokenValidationResponse(
            valid=True,
            user_id=uuid.UUID(payload["sub"]) if payload.get("sub") else None,
            email=payload.get("email"),
            roles=payload.get("roles", []),
            department_id=uuid.UUID(payload["department_id"]) if payload.get("department_id") else None,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Authentication & Login
    # ─────────────────────────────────────────────────────────────────────────

    async def authenticate_user(
        self,
        username: str,
        password: str,
        request: Request | None = None,
    ) -> TokenResponse:
        user = await self.repo.get_employee_by_identifier(username)

        if not user or not verify_password(password, user.password_hash):
            sentinel_id = str(user.employee_id) if user else "00000000-0000-0000-0000-000000000000"
            await audit(
                table_name="employees",
                record_id=sentinel_id,
                operation="LOGIN_FAILED",
                performed_by=sentinel_id,
                new_values={"username": username, "reason": "invalid_credentials"},
                request=request,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        roles = await self.repo.get_active_role_codes(user.employee_id)
        if not roles:
            roles = ["EMPLOYEE"]

        access_token = create_access_token({
            "sub": str(user.employee_id),
            "email": user.email,
            "roles": roles,
            "department_id": str(user.department_id),
        })

        token_id = uuid.uuid4()
        token_secret = secrets.token_urlsafe(64)
        client_token = f"{token_id}{_TOKEN_SEP}{token_secret}"

        token_record = None
        async with audit_ctx(
            user_id=str(user.employee_id),
            request=request,
            table_name="refresh_tokens",
            record_id=lambda: str(token_record.token_id) if token_record else "UNKNOWN",
            operation="LOGIN",
            new_values=lambda: {
                "employee_id": str(user.employee_id),
                "username": user.username,
                "roles": roles,
            },
        ):
            token_record = await self.repo.create_refresh_token(
                token_id=token_id,
                token_hash=hash_refresh_token(token_secret),
                employee_id=user.employee_id,
                expires_at=_now() + timedelta(days=7),
            )

        return self._build_login_response(user, access_token, client_token)

    # ─────────────────────────────────────────────────────────────────────────
    # Token Refresh
    # ─────────────────────────────────────────────────────────────────────────

    async def refresh_access_token(self, client_refresh_token: str) -> TokenResponse:
        if _TOKEN_SEP not in client_refresh_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")

        token_id_raw, token_secret = client_refresh_token.split(_TOKEN_SEP, 1)
        try:
            token_id = uuid.UUID(token_id_raw)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token ID format")

        stored = await self.repo.get_refresh_token(token_id)
        if not stored:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token not found")
        if stored.revoked_at or stored.expires_at < _now():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired or revoked")
        if not verify_refresh_token(token_secret, stored.token_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

        user = await self.repo.get_employee_by_id(stored.employee_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User record not found for this token")

        roles = await self.repo.get_active_role_codes(user.employee_id)
        if not roles:
            roles = ["EMPLOYEE"]

        new_access = create_access_token({
            "sub": str(user.employee_id),
            "email": user.email,
            "roles": roles,
            "department_id": str(user.department_id),
        })
        return self._build_login_response(user, new_access, client_refresh_token)

    # ─────────────────────────────────────────────────────────────────────────
    # Logout
    # ─────────────────────────────────────────────────────────────────────────

    async def logout_user(
        self,
        client_refresh_token: str,
        user_id: uuid.UUID,
        request: Request | None = None,
    ) -> dict[str, str]:
        if _TOKEN_SEP not in client_refresh_token:
            return {"message": "Invalid token format, but logged out locally"}

        token_id_raw, token_secret = client_refresh_token.split(_TOKEN_SEP, 1)
        try:
            token_id = uuid.UUID(token_id_raw)
        except ValueError:
            return {"message": "Logged out locally"}

        stored = await self.repo.get_refresh_token(token_id)
        if stored and stored.employee_id == user_id and verify_refresh_token(token_secret, stored.token_hash):
            now = _now()
            async with audit_ctx(
                user_id=str(user_id),
                request=request,
                table_name="refresh_tokens",
                record_id=str(stored.token_id),
                operation="LOGOUT",
                old_values={"revoked_at": None},
                new_values={"revoked_at": now.isoformat()},
            ):
                await self.repo.revoke_refresh_token(token_id, now)

        return {"message": "Logged out successfully"}

    # ─────────────────────────────────────────────────────────────────────────
    # Create Employee (Decoupled: Wallet provisions asynchronously via event)
    # ─────────────────────────────────────────────────────────────────────────

    async def create_employee(
        self,
        payload: SignUpRequest,
        current_user_id: uuid.UUID,
        request: Request | None = None,
        source: str = "signup",
    ) -> EmployeeResponse:
        try:
            status_id = await self.repo.validate_signup_dependencies(
                designation_id=payload.designation_id,
                department_id=payload.department_id,
                manager_id=payload.manager_id,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

        hashed_pw = hash_password(payload.password)
        new_emp = None

        async with audit_ctx(
            user_id=str(current_user_id),
            request=request,
            table_name="employees",
            record_id=lambda: str(new_emp.employee_id) if new_emp else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "username": new_emp.username if new_emp else "",
                "email": new_emp.email if new_emp else "",
                "department_id": str(new_emp.department_id) if new_emp else "",
                "designation_id": str(new_emp.designation_id) if new_emp else "",
                "source": source,
            },
        ):
            new_emp = await self.repo.create_employee(
                payload=payload,
                password_hash=hashed_pw,
                status_id=status_id,
                created_by=current_user_id,
            )

        # Publish event for the Wallet microservice to provision an initial wallet[cite: 8]
        await publish("events:employee.created", {
            "employee_id": str(new_emp.employee_id),
            "created_by": str(current_user_id),
        })

        try:
            send_welcome_email(
                email=payload.email,
                username=payload.username,
                raw_password=payload.password,
            )
        except Exception as exc:
            logger.warning("Failed to send welcome email to %s: %s", payload.email, exc)

        return EmployeeResponse.model_validate(new_emp)

    # ─────────────────────────────────────────────────────────────────────────
    # Password Reset Flow
    # ─────────────────────────────────────────────────────────────────────────

    async def request_password_reset(
        self,
        email: str,
        request: Request | None = None,
    ) -> dict[str, str]:
        user = await self.repo.get_employee_by_email(email)
        if user:
            reset_token = create_reset_token(employee_id=str(user.employee_id), email=user.email)
            try:
                send_password_reset_email(
                    email=user.email, reset_token=reset_token, username=user.username
                )
            except Exception as exc:
                logger.warning("Failed to send reset email to %s: %s", email, exc)

            await audit(
                table_name="employees",
                record_id=str(user.employee_id),
                operation="PASSWORD_RESET_REQUESTED",
                performed_by=str(user.employee_id),
                new_values={"email": email},
                request=request,
            )

        return {"message": "If your email is registered, you will receive a password reset link shortly."}

    async def reset_password(
        self,
        token: str,
        new_password: str,
        request: Request | None = None,
    ) -> dict[str, str]:
        payload = decode_reset_token(token)
        if not payload or not payload.get("sub") or not payload.get("email"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

        employee_id = uuid.UUID(payload["sub"])
        email = payload["email"]

        user = await self.repo.get_employee_by_id(employee_id)
        if not user or user.email.lower() != email.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")

        async with audit_ctx(
            user_id=str(employee_id),
            request=request,
            table_name="employees",
            record_id=str(employee_id),
            operation="PASSWORD_RESET",
            new_values={"password_changed": True, "all_tokens_revoked": True},
        ):
            await self.repo.update_password(
                employee_id=employee_id,
                new_password_hash=hash_password(new_password),
                must_change_password=False,
                updated_by=employee_id,
            )

        # Invalidate all active refresh tokens for security
        await self.repo.revoke_all_employee_tokens(employee_id, _now())

        try:
            send_password_reset_confirmation(email=user.email, username=user.username)
        except Exception as exc:
            logger.warning("Failed to send confirmation to %s: %s", email, exc)

        return {"message": "Password reset successful. Please login with your new password."}

    async def change_password(
        self,
        employee_id: uuid.UUID,
        new_password: str,
        request: Request | None = None,
    ) -> dict[str, str]:
        user = await self.repo.get_employee_by_id(employee_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        async with audit_ctx(
            user_id=str(employee_id),
            request=request,
            table_name="employees",
            record_id=str(employee_id),
            operation="PASSWORD_CHANGE",
            new_values={"password_changed": True, "must_change_password": False},
        ):
            await self.repo.update_password(
                employee_id=employee_id,
                new_password_hash=hash_password(new_password),
                must_change_password=False,
                updated_by=employee_id,
            )

        return {"message": "Password updated successfully."}