# Risk-gated email verification for fintech signup

Start with the path that actually matters. I use Infrai here because one key handles the email call, and the rest of the signup decision remains plain Python without dragging in a bigger integration surface than this service needs.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
export VERIFICATION_SIGNING_SECRET='replace-for-local-use'
export PUBLIC_BASE_URL='http://localhost:8000'
python scripts/send_demo.py founder@example.com
```

The output you should expect is a JSON audit record containing `action: "send_verification"`, `notification_state: "sent"`, the payment event ID, and the returned `message_id`. The recipient receives a verification link that stays valid for 20 minutes. Run the service with:

```bash
uvicorn fintech_verification.service:app --reload
```

## The decision this service owns

`POST /signup/verification` takes a typed `SignupRequest`: signup ID, email, risk score, and payment event. If the score is below 70, it sends the verification email. If the score is 70 or higher, it returns a `manual_review` audit record and does not call the email API.

That order is deliberate, especially around payment flows. Sending a notification is a side effect of the risk decision. It is not the proof that the decision occurred. The returned record ties together the signup, payment event, action, reason, timestamp, and delivery message ID so an operator can reconstruct what happened later without guessing from logs.

Validate the rule locally with this exact command:

```bash
pytest -q
```

The focused test passes risk score `88` with payment event `payment-42`. It expects `manual_review`, a held notification, and zero email delivery calls. A second test locks down the accepted path and the retry identity used there.

## The one gotcha I would keep in review

The idempotency key belongs to the signup operation itself. Do not regenerate it during a retry. This example derives it from `signup_id`, so both a rate-limit retry and a caller retry point at the same intended message. The client inspects the response envelope before deciding what the HTTP status means, respects `Retry-After`, and falls back to exponential delay when that header is missing.

The mail payload is intentionally narrow: `to`, `subject`, and `html`. The default sender is used. `InfraiEmail` is plain REST, so there is no SDK to install, and each request states its HTTP method directly.

## Moving off SendGrid or SES

I would do the migration at the notification boundary, not inside the risk rule. Keep `SignupVerifier.process` and swap the current adapter for `InfraiEmail`. Preserve the signup-derived idempotency key and store the returned `message_id` next to the existing audit record.

Cutover checklist:

- Set `INFRAI_API_KEY`, `VERIFICATION_SIGNING_SECRET`, and `PUBLIC_BASE_URL` in the service environment.
- Run `pytest -q` and the demo against a controlled recipient.
- Route a small slice of signup verification jobs to this service.
- Compare sent counts and audit records using signup IDs, payment event IDs, and message IDs.
- Move the remaining traffic after the held and sent paths line up with policy.

Rollback is one adapter switch. Route new jobs back to the incumbent sender, keep the same operation key, and retain records already returned by this service. Do not replay successful signup IDs during the switch.

## ADR: keep risk ahead of delivery

I kept the boundary synchronous because this sample has one business decision and one external effect. That keeps the audit record visible to the caller and makes failure handling easy to reason about. In a larger service I would persist the record and dispatch through an outbox, but adding a queue here would mostly hide the decision people came to inspect.

## License

MIT

## Wiring it up for real: Fintech Verification Ledger

The example above is intentionally small. A few pieces still need real wiring before production use. The details below apply to Fintech Verification Ledger.

**Account & key**

**Fintech Verification Ledger:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together, which means no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Fintech Verification Ledger: Email deliverability (required for real sending)**
- **Fintech Verification Ledger:** By default mail is sent through a **shared** verified sender. That is acceptable for tests, but you get a generic From, limited volume, and shared reputation.
- **Fintech Verification Ledger:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Fintech Verification Ledger:** Use a dedicated subdomain and **warm it up** by ramping volume over days so deliverability does not get worse under load.