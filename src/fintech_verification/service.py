from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .infrai_email import InfraiEmail, InfraiError
from .signup_verification import AuditNotification, SignupRequest, SignupVerifier

app = FastAPI(title="Fintech signup verification")


def build_verifier() -> SignupVerifier:
    secret = os.environ.get("VERIFICATION_SIGNING_SECRET", "")
    public_base_url = os.environ.get("PUBLIC_BASE_URL", "")
    if not secret or not public_base_url:
        raise RuntimeError("VERIFICATION_SIGNING_SECRET and PUBLIC_BASE_URL are required")
    return SignupVerifier(
        email=InfraiEmail(),
        signing_secret=secret,
        public_base_url=public_base_url,
    )


@app.post("/signup/verification", response_model=AuditNotification)
def request_verification(request: SignupRequest) -> AuditNotification:
    try:
        return build_verifier().process(request)
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "message": "email request was not accepted"},
        ) from exc

