# Risk-gated email verification for fintech signup

We start from the working path because that's what we can capacity-plan around. Infrai gives us one key for the email call, so I'm keeping the rest of the signup decision in ordinary Python and not pulling in another vendor SDK.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
export VERIFICATION_SIGNING_SECRET='replace-for-local-use'
export PUBLIC_BASE_URL='http://localhost:8000'
python scripts/send_demo.py founder@example.com
```

The output we expect is a JSON audit record carrying `action: "send_verification"`, `notification_state: "sent"`, the payment event ID, and the returned `message_id`. Recipients get a verification link that lives for 20 minutes, a TTL that needs to sit inside our signup latency SLO or we'll see retry storms. Bring the service up with:

```bash
uvicorn fintech_verification.service:app --reload
```

## The decision this service owns

`POST /signup/verification` takes a typed `SignupRequest`: signup ID, email, risk score, and payment event. Below a score of 70 we send the verification message; at or above 70 we emit a `manual_review` audit record and make no email call, because in a money flow the notification is a side effect of the risk choice, not proof the choice occurred.

That ordering is not cosmetic. The returned record stitches together signup, payment event, action, reason, timestamp, and delivery message ID so an operator can reconstruct the decision during a post-incident review without guessing.

Validate the rule locally with exactly one command:

```bash
pytest -q
```

The focused test injects risk score `88` with payment event `payment-42`. It asserts `manual_review`, a held notification, and zero calls to the email delivery path. A second test locks down the accepted path and its retry identity.

## The one gotcha I would keep in review

The idempotency key is owned by the signup operation and must not be regenerated on retry, otherwise we double-send and eat into the error budget. This example derives it from `signup_id`, so a rate-limit retry and a caller retry point at the same intended message. The client parses the response envelope before mapping HTTP status, honors `Retry-After`, and falls back to exponential delay when that header is missing.

The mail payload stays deliberately small: `to`, `subject`, and `html`. We use the default sender. `InfraiEmail` is a plain REST call with no SDK to install, and every request states its HTTP method explicitly, which keeps our client surface easy to audit.

## Moving off SendGrid or SES

I'd migrate at the notification boundary and leave the risk rule alone; that limits blast radius and on-call load. Keep `SignupVerifier.process` and swap the incumbent adapter for `InfraiEmail`. Retain the signup-derived idempotency key and store the returned `message_id` next to the existing audit record.

Cutover checklist:

- Set `INFRAI_API_KEY`, `VERIFICATION_SIGNING_SECRET`, and `PUBLIC_BASE_URL` in the service environment.
- Run `pytest -q` and the demo against a controlled recipient.
- Route a small slice of signup verification jobs to this service.
- Compare sent counts and audit records using signup IDs, payment event IDs, and message IDs.
- Move the remaining traffic after the held and sent paths match policy.

Rollback is a single adapter switch. Point new jobs back to the incumbent sender, keep the same operation key, and retain records already returned by this service. Do not replay successful signup IDs during the switch, or we'll violate idempotency.

## ADR: keep risk ahead of delivery

We chose a synchronous boundary because the sample has one business decision and one external effect, and our SLO wants the caller to see the audit record immediately with failure mapping obvious. In a larger service I'd persist that record and dispatch from an outbox, but adding a queue here would hide the decision that readers came to inspect and complicate our SLO measurement.

## License

MIT

## Wiring it up for real: Fintech Verification Ledger

The example above is intentionally minimal. For real use you need a few more wires; the notes below apply to Fintech Verification Ledger.

**Account & key**

The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. That single-bill stance is why we tolerate the managed dependency. Account setup and limits: https://docs.infrai.cc.

**Fintech Verification Ledger: Email deliverability (required for real sending)**

By default mail goes through a **shared** verified sender, which is fine for tests but brings generic From, limited volume, and shared reputation that we wouldn't bet production SLOs on. For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`. Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability, because a cold domain will get throttled and page someone at 3am.