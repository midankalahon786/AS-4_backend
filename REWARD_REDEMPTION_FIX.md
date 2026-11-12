# Reward Catalog Redemption Fix

## 1. Problem Summary
Users were unable to redeem rewards from the catalog via the API (`POST /aabhar/v1/rewards/redeem` or `POST /redeem`). Attempts to redeem resulted in `500 Internal Server Error` or `422 Unprocessable Entity`.

---

## 2. Root Cause Analysis

1. **SQLAlchemy `NoReferencedTableError` on `RewardHistory.wallet_id`**:
   - In `src/rewards/models.py`, `RewardHistory` defines:
     ```python
     wallet_id: Mapped[uuid.UUID] = mapped_column(
         UUID(as_uuid=True), ForeignKey("wallets.wallet_id", ondelete="CASCADE"), nullable=False
     )
     ```
   - However, `Wallet` from `src.wallet.models` was never imported into `src/rewards/models.py`.
   - Consequently, SQLAlchemy's `Base.metadata` in the rewards microservice runtime had no entry for the `wallets` table.
   - When `self.db.flush()` was invoked in `claim_reward_atomic`, SQLAlchemy raised:
     `sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column 'reward_history.wallet_id' could not find table 'wallets' with which to generate a foreign key to target column 'wallet_id'`.

2. **`CurrentUser` Pydantic Validation Error in Authentication Dependency**:
   - In `src/common/dependencies.py`, `CurrentUser` declared `email: str`.
   - When `get_current_user` authenticated the token, `data.get("email", "")` was evaluated. When `data` from the auth service contained `"email": None`, `dict.get("email", "")` returns `None` (since the key exists).
   - Passing `None` to `CurrentUser(..., email=None, ...)` triggered `ValidationError: email: Input should be a valid string`.

3. **`NotificationService` Initializer Type Mismatch**:
   - In `src/rewards/dependencies.py`, `notif_service = NotificationService(db, redis=redis_conn)` passed `db: AsyncSession` directly.
   - `NotificationService.__init__` expected `repo: INotificationRepository`.
   - When calling `create_notification`, it failed with:
     `AttributeError: 'AsyncSession' object has no attribute 'create_notification'`.

4. **`Transaction.status_master` Mapper Error in Wallet Service**:
   - In `src/wallet/models.py`, `Transaction.status_master` was declared as:
     `relationship("src.employees.models.StatusMaster", lazy="joined")`.
   - Dotted module names in SQLAlchemy relationship definitions fail mapper resolution with:
     `InvalidRequestError: When initializing mapper Mapper[Transaction(transactions)], expression 'src.employees.models.StatusMaster' failed to locate a name`.
   - This caused failures during wallet transaction recording.

5. **Strict `points` Requirement in `RedeemRewardRequest`**:
   - `RedeemRewardRequest` required `points: int = Field(..., strict=True)`.
   - When frontends send `{ "catalog_id": "<uuid>" }` expecting to redeem at the catalog item's default price, FastAPI returned `422 Unprocessable Entity`.

---

## 3. Changes Made

### A. Rewards Microservice
- **`src/rewards/models.py`**:
  - Imported `from src.wallet.models import Wallet`.
  - Added `wallet: Mapped["Wallet"] = relationship("Wallet", foreign_keys=[wallet_id])` to `RewardHistory`.
- **`src/rewards/schemas.py`**:
  - Made `points` optional in `RedeemRewardRequest`: `points: int | None = Field(default=None, strict=True, gt=0)`.
  - Added `RedeemRewardRequestOptionalCatalog` for path-parameter based redemptions.
- **`src/rewards/repository.py`**:
  - Imported `Wallet` from `src.wallet.models`.
  - Added direct fallback methods: `get_wallet_by_employee_id` and `get_wallet_by_id`.
- **`src/rewards/service.py`**:
  - Updated `grant_reward` to default `points = request.points if request.points is not None else reward_item.default_points`.
  - Added database fallback if `internal_client.get_wallet_by_id` fails or returns 404.
  - Added database fallback in `get_wallet_id_for_user` to query `self.repo.get_wallet_by_employee_id` if HTTP service call fails.
  - Added database fallback in `get_history`.
- **`src/rewards/router.py`**:
  - Updated `POST /redeem` to handle both explicit and default points.
  - Added route `POST /catalog/{catalog_id}/redeem` allowing users to redeem directly from a catalog item view.
- **`src/rewards/main.py`**:
  - Registered `POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem` in `ROLE_OVERRIDES` for `["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"]`.
  - Registered route title in `ROUTE_TITLES`.
- **`src/rewards/dependencies.py`**:
  - Fixed `NotificationService` instantiation: instantiated `SQLAlchemyNotificationRepository(db)` and passed it to `NotificationService`.

### B. Common & Cross-Service Fixes
- **`src/common/dependencies.py`**:
  - Updated `CurrentUser` schema: `email: str | None = ""` to allow nullable email.
  - Updated `get_current_user`: safely coalesced email via `data.get("email") or ""` and `payload.get("email") or ""`.
- **`src/notifications/service.py`**:
  - Added polymorphic support to `NotificationService.__init__`: if an `AsyncSession` is passed instead of a repository, it automatically wraps it in `SQLAlchemyNotificationRepository(repo)`.
- **`src/wallet/models.py`**:
  - Imported `from src.employees.models import Employee, StatusMaster`.
  - Updated relationship to `"StatusMaster"` instead of `"src.employees.models.StatusMaster"`.

---

## 4. Verification & Testing

1. **Unit & Integration Tests (`src/rewards/tests/test_redemption.py`)**:
   - `test_grant_reward_success`: PASSED
   - `test_grant_reward_default_points_when_omitted`: PASSED
   - `test_grant_reward_insufficient_points`: PASSED
   - `test_grant_reward_out_of_stock`: PASSED
   - `test_grant_reward_points_outside_range`: PASSED
   - `test_get_wallet_id_fallback_to_db`: PASSED
   - `test_api_redeem_endpoints_with_auth`: PASSED
   - Result: **7/7 tests passed**.

2. **Live Microservice HTTP Verification**:
   - `POST http://localhost:8006/aabhar/v1/rewards/redeem` (with points) -> `HTTP 201 Created`
   - `POST http://localhost:8006/aabhar/v1/rewards/redeem` (without points, using item default) -> `HTTP 201 Created`
   - `POST http://localhost:8006/catalog/{catalog_id}/redeem` -> `HTTP 201 Created`
   - `GET http://localhost:8006/aabhar/v1/rewards/history/me` -> `HTTP 200 OK` (returns newly redeemed history records)
   - Confirmed asynchronous Redis stream consumption: `transactions` table correctly recorded point deductions and `wallets.available_points` decremented accurately.
