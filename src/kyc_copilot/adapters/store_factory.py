"""Select sqlite or postgres for the copilot knowledge store. Never open mock.sqlite."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from kyc_copilot.adapters.sqlite_store import SqliteKnowledgeStore
from kyc_copilot.contracts.interfaces import KnowledgeStore


def resolve_store_target(
    db: str | None = None,
    dsn: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """`--dsn` then `KYC_DATABASE_URL` then `--db`. Cloud Run needs only the env var."""
    if dsn and dsn.strip():
        return dsn.strip()
    environ = os.environ if env is None else env
    url = (environ.get("KYC_DATABASE_URL") or "").strip()
    if url:
        return url
    if db:
        return str(db)
    raise ValueError("No knowledge store target: pass --dsn, KYC_DATABASE_URL, or --db")


def open_knowledge_store(target: str) -> KnowledgeStore:
    """`:memory:` / `*.sqlite` → sqlite; `postgres(ql)://` → postgres; `mock.sqlite` refused."""
    if Path(target).name == "mock.sqlite":
        raise ValueError("Refusing to use the mock service's state file; choose another --db path.")
    if target.startswith("postgresql://") or target.startswith("postgres://"):
        from kyc_copilot.adapters.postgres_store import PostgresKnowledgeStore

        return PostgresKnowledgeStore(target)
    if target == ":memory:" or target.endswith(".sqlite"):
        return SqliteKnowledgeStore(target)
    raise ValueError(f"Unrecognized knowledge store target: {target!r}")
