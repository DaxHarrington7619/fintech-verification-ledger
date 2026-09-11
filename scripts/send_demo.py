from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime

from fintech_verification.infrai_email import InfraiEmail
from fintech_verification.signup_verification import PaymentEvent, SignupRequest, SignupVerifier


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one risk-approved verification email")
    parser.add_argument("email")
    args = parser.parse_args()
    verifier = SignupVerifier(
        email=InfraiEmail(),
        signing_secret=os.environ["VERIFICATION_SIGNING_SECRET"],
        public_base_url=os.environ["PUBLIC_BASE_URL"],
    )
    result = verifier.process(
        SignupRequest(
            signup_id="demo-signup-001",
            email=args.email,
            risk_score=12,
            payment_event=PaymentEvent(
                event_id="payment-authorized-001",
                customer_id="demo-customer",
                amount_minor=2500,
                currency="USD",
                occurred_at=datetime.now(UTC),
            ),
        )
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

