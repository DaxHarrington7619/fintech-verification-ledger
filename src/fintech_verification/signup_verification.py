from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlencode

from pydantic import BaseModel, EmailStr, Field

from .infrai_email import InfraiEmail


class PaymentEvent(BaseModel):
    event_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    amount_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    occurred_at: datetime


class SignupRequest(BaseModel):
    signup_id: str = Field(min_length=1)
    email: EmailStr
    risk_score: int = Field(ge=0, le=100)
    payment_event: PaymentEvent


class RiskAction(StrEnum):
    SEND_VERIFICATION = "send_verification"
    MANUAL_REVIEW = "manual_review"


class NotificationState(StrEnum):
    SENT = "sent"
    HELD = "held"


class AuditNotification(BaseModel):
    signup_id: str
    payment_event_id: str
    action: RiskAction
    notification_state: NotificationState
    reason: str
    recorded_at: datetime
    message_id: str | None = None


@dataclass(frozen=True)
class SignupVerifier:
    email: InfraiEmail
    signing_secret: str
    public_base_url: str
    review_threshold: int = 70

    def process(self, request: SignupRequest, *, now: datetime | None = None) -> AuditNotification:
        recorded_at = now or datetime.now(UTC)
        if request.risk_score >= self.review_threshold:
            return AuditNotification(
                signup_id=request.signup_id,
                payment_event_id=request.payment_event.event_id,
                action=RiskAction.MANUAL_REVIEW,
                notification_state=NotificationState.HELD,
                reason="risk threshold reached before notification",
                recorded_at=recorded_at,
            )

        verification_url = self._verification_url(request, recorded_at)
        message_id = self.email.send_verification(
            to=str(request.email),
            verification_url=verification_url,
            idempotency_key=f"signup-verification:{request.signup_id}",
        )
        return AuditNotification(
            signup_id=request.signup_id,
            payment_event_id=request.payment_event.event_id,
            action=RiskAction.SEND_VERIFICATION,
            notification_state=NotificationState.SENT,
            reason="risk accepted; verification requested",
            recorded_at=recorded_at,
            message_id=message_id,
        )

    def _verification_url(self, request: SignupRequest, now: datetime) -> str:
        expires_at = int((now + timedelta(minutes=20)).timestamp())
        payload = f"{request.signup_id}:{request.email}:{expires_at}"
        signature = hmac.new(
            self.signing_secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        query = urlencode(
            {"signup_id": request.signup_id, "expires_at": expires_at, "signature": signature}
        )
        return f"{self.public_base_url.rstrip('/')}/verify-email?{query}"

