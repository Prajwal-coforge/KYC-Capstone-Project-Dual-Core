"""HTTP client for the mock enterprise service: the four read tools and review submission.

Deliberately has no operation for creating records or approving reviews: those are human-only.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from kyc_copilot.contracts.models import ToolResult

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


class _Circuit:
    """Per-tool breaker. Opens after one exhausted fetch. One probe after cooldown."""

    def __init__(self):
        self.opened_at: float | None = None
        self.probing = False

    def state(self, now: float, cooldown: float) -> str:
        if self.opened_at is None:
            return "closed"
        if now - self.opened_at >= cooldown and not self.probing:
            return "half_open"
        return "open"

    def before_call(self, now: float, cooldown: float) -> str | None:
        """Return the circuit state if a call is allowed, else None."""
        state = self.state(now, cooldown)
        if state == "open":
            return None
        if state == "half_open":
            self.probing = True
        return state

    def succeed(self) -> None:
        self.opened_at = None
        self.probing = False

    def fail(self, now: float) -> None:
        self.opened_at = now
        self.probing = False


class ToolClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        max_attempts: int = MAX_ATTEMPTS,
        backoff_seconds: float = 0.05,
        circuit_cooldown: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.circuit_cooldown = circuit_cooldown
        self._circuits: dict[str, _Circuit] = {}
        self._now = time.monotonic
        self.sleep = time.sleep

    def reset_circuits(self) -> None:
        """Start a new case with a closed breaker.

        A second fetch in the same case still trips it.
        """
        self._circuits.clear()

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
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
        circuit = self._circuits.setdefault(tool, _Circuit())
        now = self._now()
        state = circuit.before_call(now, self.circuit_cooldown)
        if state is None:
            return ToolResult(tool, False, None, 0, "circuit_open", 0.0, "open")
        path = f"/v1/cases/{urllib.parse.quote(case_id, safe='')}/{tool}"
        started = self._now()
        error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = self._request("GET", path)
                if not isinstance(payload, dict) or not isinstance(payload.get("source_id"), str):
                    raise _Retryable("invalid_response")
                circuit.succeed()
                return ToolResult(tool, True, payload, attempt, None, self._now() - started, state)
            except _Final as exc:
                # 404/400 are not an outage; do not open the breaker
                circuit.succeed()
                return ToolResult(
                    tool, False, None, attempt, exc.error, self._now() - started, state
                )
            except _Retryable as exc:
                error = exc.error
                if attempt < self.max_attempts and self.backoff_seconds:
                    self.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        circuit.fail(self._now())
        return ToolResult(
            tool, False, None, self.max_attempts, error, self._now() - started, "open"
        )

    def list_cases(self) -> list[dict]:
        return self._request("GET", "/v1/cases")["cases"]

    def submit_review(self, case_id: str, draft: dict) -> dict:
        """Ask a human to review the draft. Returns review_id, pending status and draft hash."""
        return self._request("POST", "/v1/reviews", {"case_id": case_id, "draft": draft})
