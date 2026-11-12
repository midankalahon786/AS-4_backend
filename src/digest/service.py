"""
src/digest/service.py
─────────────────────
Digest service layer orchestrating query resolution and HTML email delivery[cite: 37].
Powered by SQLAlchemy 2.0 AsyncSession[cite: 37].
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.digest.email_builder import build_digest_html
from src.digest.queries import fetch_weekly_digest_data
from src.digest.schemas import DigestResponse, WeeklyDigestData
from src.notifications.email_sender import EmailSender

logger = logging.getLogger(__name__)


class DigestService:
    def __init__(self, session: AsyncSession, email_sender: EmailSender) -> None:
        self.session = session
        self.sender = email_sender

    async def get_digest_data(
        self,
        week_start: datetime | None = None,
        manager_id: UUID | None = None,
    ) -> WeeklyDigestData:
        return await fetch_weekly_digest_data(
            self.session,
            week_start=week_start,
            manager_id=manager_id,
        )

    async def send_digest_email(
        self,
        *,
        manager_email: str,
        manager_id: UUID | None = None,
        week_start: datetime | None = None,
    ) -> DigestResponse:
        # Guard: Reject future week_start immediately[cite: 37]
        if week_start is not None:
            now_utc = datetime.now(tz=timezone.utc)
            ws = week_start if week_start.tzinfo else week_start.replace(tzinfo=timezone.utc)
            if ws > now_utc:
                return DigestResponse(
                    success=False,
                    message="week_start must not be in the future.",
                )

        try:
            data = await fetch_weekly_digest_data(
                self.session,
                week_start=week_start,
                manager_id=manager_id,
            )
            subject, html = build_digest_html(data)

            await self.sender.send_notification_email(
                to_email=manager_email,
                subject=subject,
                body_html=html,
            )

            logger.info(
                "Weekly digest sent to %s | manager=%s week=%s recognitions=%d",
                manager_email,
                manager_id or "platform-wide",
                data.week_start.date(),
                data.total_recognitions,
            )
            return DigestResponse(
                success=True,
                message=f"Digest sent to {manager_email}",
                data=data,
            )

        except Exception:
            logger.exception(
                "DigestService: failed to send digest to %s (manager=%s)",
                manager_email,
                manager_id,
            )
            return DigestResponse(
                success=False,
                message="Failed to generate or send digest. Check server logs.",
            )