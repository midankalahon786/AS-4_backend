"""
src/webhooks/router.py
──────────────────────
Webhooks router — thin HTTP layer only[cite: 30].
Mounted inside Employee Service (src/employees/main.py)[cite: 30].
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from src.common.dependencies import CurrentUser, check_route_permission
from src.webhooks.dependencies import get_webhook_service
from src.webhooks.schemas import HrisWebhookEvent, WebhookResponse
from src.webhooks.service import WebhookService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "/hris",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="HRIS push webhook",
)
async def hris_webhook(
    request: Request,
    event: HrisWebhookEvent,
    service: WebhookService = Depends(get_webhook_service),
    _: CurrentUser = Depends(check_route_permission),
):
    """
    Receives HRIS push events and syncs employee data[cite: 30].

    Supported events:
      - employee.created[cite: 30]
      - employee.updated[cite: 30]
      - employee.status_changed[cite: 30]

    Security: HMAC-SHA256 signature verified from X-Webhook-Signature header[cite: 30].
    Idempotency: supply event_id in payload to prevent duplicate processing[cite: 30].
    """
    result = await service.handle_hris_event(request, event)
    return WebhookResponse(**result)