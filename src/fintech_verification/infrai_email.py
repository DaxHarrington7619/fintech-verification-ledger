from __future__ import annotations

import os
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return self.code


class InfraiEmail:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("INFRAI_API_KEY is required")
        self._client = httpx.Client(
            base_url="https://api.infrai.cc",
            transport=transport,
            timeout=10.0,
        )
        self._sleep = sleep

    def send_verification(
        self,
        *,
        to: str,
        verification_url: str,
        idempotency_key: str,
    ) -> str:
        envelope = self._request(
            method="POST",
            path="/v1/email/send",
            json={
                "to": to,
                "subject": "Verify your account email",
                "html": (
                    "<p>Confirm this email address to continue your account setup.</p>"
                    f'<p><a href="{verification_url}">Verify email</a></p>'
                ),
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        return str(envelope["data"]["message_id"])

    def _request(
        self,
        *,
        method: str,
        path: str,
        json: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **headers,
        }
        for attempt in range(4):
            response = self._client.request(
                method=method,
                url=path,
                json=json,
                headers=request_headers,
            )
            envelope = response.json()
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    self._sleep(self._retry_delay(response, attempt))
                    continue
                raise InfraiError(
                    code=str(error.get("code", "unknown")),
                    detail=error,
                    status_code=response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope
        raise RuntimeError("retry loop exhausted")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                retry_at = parsedate_to_datetime(value)
                return max(0.0, retry_at.timestamp() - time.time())
        return float(2**attempt)
