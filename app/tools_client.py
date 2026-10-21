"""HTTP client for the mock enterprise service: the four read tools and review submission.

Deliberately has no operation for creating records or approving reviews: those are human-only.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

TOOLS = ("customer", "registry", "screening", "transaction-summary")
MAX_ATTEMPTS = 3  # KYC-SCOPE-01: retry at most twice, then stop and escalate


class ServiceError(Exception):
    def __init__(self, error: str):
        super().__init__(error)
        self.error = error


class _Retryable(ServiceError):
    pass


class _Final(ServiceError):
    pass


@dataclass(frozen=True)
class ToolResult:
    tool: str
    ok: bool
    payload: dict | None
    attempts: int
    error: str | None = None
    seconds: float = 0.0

    @property
    def source_id(self) -> str | None:
        return self.payload.get("source_id") if self.payload else None


class ToolClient:
    def __init__(self, base_url: str, timeout: float = 5.0, max_attempts: int = MAX_ATTEMPTS,
                 backoff_seconds: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                raise _Retryable("upstream_timeout") from exc
            if exc.code >= 500:
                raise _Retryable(f"http_{exc.code}") from exc
            raise _Final("not_found" if exc.code == 404 else f"http_{exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise _Retryable("connection_error") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise _Retryable("invalid_response") from exc

    def fetch(self, case_id: str, tool: str) -> ToolResult:
        if tool not in TOOLS:
            raise ValueError(f"unknown tool: {tool}")
        path = f"/v1/cases/{urllib.parse.quote(case_id, safe='')}/{tool}"
        started = time.monotonic()
        error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = self._request("GET", path)
                if not isinstance(payload, dict) or not isinstance(payload.get("source_id"), str):
                    raise _Retryable("invalid_response")
                return ToolResult(tool, True, payload, attempt, None, time.monotonic() - started)
            except _Final as exc:
                return ToolResult(tool, False, None, attempt, exc.error, time.monotonic() - started)
            except _Retryable as exc:
                error = exc.error
                if attempt < self.max_attempts and self.backoff_seconds:
                    time.sleep(self.backoff_seconds * attempt)
        return ToolResult(tool, False, None, self.max_attempts, error, time.monotonic() - started)

    def list_cases(self) -> list[dict]:
        return self._request("GET", "/v1/cases")["cases"]

    def submit_review(self, case_id: str, draft: dict) -> dict:
        """Ask a human to review the draft. Returns review_id, pending status and draft hash."""
        return self._request("POST", "/v1/reviews", {"case_id": case_id, "draft": draft})
