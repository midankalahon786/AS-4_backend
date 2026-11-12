"""
src/auth/router.py
──────────────────
Authentication & Employee Identity Router.
Powered by AuthService with SQLAlchemy 2.0 async session dependency injection.
"""
from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.security import OAuth2PasswordBearer

from src.auth.dependencies import get_auth_service
from src.auth.schemas import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    EmployeeResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SignUpRequest,
    TokenResponse,
    TokenValidationRequest,
    TokenValidationResponse,
)
from src.auth.service import AuthService
from src.common.dependencies import CurrentUser, check_route_permission
from src.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/aabhar/v1/auth/login")
router = APIRouter(tags=["Authentication"])

REQUIRED_COLUMNS = {"username", "email", "password", "designation_id", "department_id"}


def _parse_csv(content: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


def _parse_xlsx(content: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="openpyxl is not installed on the system",
        )
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        return []
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    return [
        {headers[i]: (str(c).strip() if c is not None else "") for i, c in enumerate(row)}
        for row in rows[1:]
    ]


def _row_to_signup(row: dict) -> tuple[SignUpRequest | None, str | None]:
    row = {k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    missing = REQUIRED_COLUMNS - set(row.keys())
    if missing:
        return None, f"Missing columns: {', '.join(sorted(missing))}"
    for col in REQUIRED_COLUMNS:
        if not row.get(col):
            return None, f"'{col}' is empty"
    try:
        return SignUpRequest(
            username=row["username"],
            email=row["email"],
            password=row["password"],
            designation_id=UUID(row["designation_id"]),
            department_id=UUID(row["department_id"]),
            manager_id=UUID(row["manager_id"]) if row.get("manager_id") else None,
            date_of_birth=row["date_of_birth"] if row.get("date_of_birth") else None,
        ), None
    except Exception as exc:
        return None, str(exc)


# ══════════════════════════════════════════════════════════════
#  Public Endpoints (No Authentication Required)
# ══════════════════════════════════════════════════════════════

@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await service.authenticate_user(
        username=payload.username,
        password=payload.password,
        request=request,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await service.refresh_access_token(payload.refresh_token)


@router.post("/logout")
async def logout(
    request: Request,
    payload: LogoutRequest,
    token: str = Depends(oauth2_scheme),
    service: AuthService = Depends(get_auth_service),
):
    user_data = decode_token(token)
    if not user_data or not user_data.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )
    return await service.logout_user(
        client_refresh_token=payload.refresh_token,
        user_id=UUID(user_data["sub"]),
        request=request,
    )


@router.post("/validate", response_model=TokenValidationResponse)
async def validate_token_endpoint(
    payload: TokenValidationRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await service.validate_token(payload.token)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await service.request_password_reset(payload.email, request)


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password_endpoint(
    request: Request,
    payload: ResetPasswordRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await service.reset_password(payload.token, payload.new_password, request)


# ══════════════════════════════════════════════════════════════
#  Protected Endpoints
# ══════════════════════════════════════════════════════════════

@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password_endpoint(
    request: Request,
    payload: ChangePasswordRequest,
    token: str = Depends(oauth2_scheme),
    service: AuthService = Depends(get_auth_service),
):
    """Allows an authenticated user to change their password and clears must_change_password."""
    user_data = decode_token(token)
    if not user_data or not user_data.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )
    return await service.change_password(
        employee_id=UUID(user_data["sub"]),
        new_password=payload.new_password,
        request=request,
    )


@router.post("/signup", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    request: Request,
    payload: SignUpRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: AuthService = Depends(get_auth_service),
):
    """Creates an employee. Wallet is provisioned asynchronously via Redis stream event."""
    current_id = UUID(str(current_user.id))
    return await service.create_employee(
        payload=payload,
        current_user_id=current_id,
        request=request,
        source="signup",
    )


@router.post(
    "/bulk-import",
    status_code=status.HTTP_200_OK,
    summary="Bulk import employees via CSV or XLSX",
)
async def bulk_import_employees(
    request: Request,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(check_route_permission),
    service: AuthService = Depends(get_auth_service),
):
    """
    Parses and provisions employee records.
    Each successful row publishes an employee.created event so the
    Wallet service provisions wallets asynchronously.
    """
    filename = (file.filename or "").lower()
    if not (filename.endswith(".csv") or filename.endswith(".xlsx")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv and .xlsx files are supported",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    try:
        rows = _parse_csv(content) if filename.endswith(".csv") else _parse_xlsx(content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parse error: {exc}",
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has no data rows",
        )

    current_id = UUID(str(current_user.id))
    results, succeeded, failed = [], 0, 0

    for idx, row in enumerate(rows, start=2):
        payload, err = _row_to_signup(row)
        if err:
            failed += 1
            results.append({
                "row": idx,
                "username": row.get("username"),
                "email": row.get("email"),
                "status": "error",
                "error": err,
            })
            continue
        try:
            emp = await service.create_employee(
                payload=payload,
                current_user_id=current_id,
                request=request,
                source="bulk_import",
            )
            succeeded += 1
            results.append({
                "row": idx,
                "username": emp.username,
                "email": emp.email,
                "status": "success",
                "employee_id": str(emp.employee_id),
            })
        except HTTPException as exc:
            failed += 1
            results.append({
                "row": idx,
                "username": row.get("username"),
                "email": row.get("email"),
                "status": "error",
                "error": exc.detail,
            })
        except Exception as exc:
            failed += 1
            results.append({
                "row": idx,
                "username": row.get("username"),
                "email": row.get("email"),
                "status": "error",
                "error": str(exc),
            })

    return {
        "total": len(rows),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }