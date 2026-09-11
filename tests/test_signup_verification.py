from datetime import UTC, datetime

from fintech_verification.signup_verification import (
    NotificationState,
    PaymentEvent,
    RiskAction,
    SignupRequest,
    SignupVerifier,
)


class RecordingEmail:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def send_verification(self, **values: str) -> str:
        self.calls.append(values)
        return "msg-audit-42"


def signup(risk_score: int) -> SignupRequest:
    return SignupRequest(
        signup_id="signup-42",
        email="founder@example.com",
        risk_score=risk_score,
        payment_event=PaymentEvent(
            event_id="payment-42",
            customer_id="customer-9",
            amount_minor=9900,
            currency="USD",
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )


def test_high_risk_signup_is_held_before_email() -> None:
    email = RecordingEmail()
    verifier = SignupVerifier(email=email, signing_secret="test-secret", public_base_url="https://app.example.com")  # type: ignore[arg-type]

    record = verifier.process(signup(88), now=datetime(2026, 1, 2, tzinfo=UTC))

    assert record.action is RiskAction.MANUAL_REVIEW
    assert record.notification_state is NotificationState.HELD
    assert record.payment_event_id == "payment-42"
    assert email.calls == []


def test_accepted_signup_sends_once_with_stable_retry_key() -> None:
    email = RecordingEmail()
    verifier = SignupVerifier(email=email, signing_secret="test-secret", public_base_url="https://app.example.com")  # type: ignore[arg-type]

    record = verifier.process(signup(12), now=datetime(2026, 1, 2, tzinfo=UTC))

    assert record.action is RiskAction.SEND_VERIFICATION
    assert record.message_id == "msg-audit-42"
    assert email.calls[0]["idempotency_key"] == "signup-verification:signup-42"
    assert "expires_at=" in email.calls[0]["verification_url"]

