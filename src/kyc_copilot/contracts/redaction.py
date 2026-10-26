"""Restricted-value handling and JSON fragments. Stdlib only; no I/O."""

from __future__ import annotations

import json
from typing import Any

# Fields that must never reach outputs, logs, traces or disk (KYC-SCOPE-01).
RESTRICTED_KEYS = frozenset({"private_token"})


def redact(value: Any) -> Any:
    """Copy of value with restricted keys removed at any depth."""
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k not in RESTRICTED_KEYS}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def canonical_json(payload: Any) -> str:
    """Same normalization the evaluator applies to tool evidence: sorted keys, standard spaces."""
    return json.dumps(payload, sort_keys=True)


def json_fragment(key: str, value: Any) -> str:
    """A quotable `"key": value` excerpt of canonical_json output."""
    return f"{json.dumps(key)}: {json.dumps(value)}"
