"""PostgreSQL adapter for the copilot KnowledgeStore (psycopg v3). Never opens mock.sqlite."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row

from kyc_copilot.adapters.sqlite_store import SCHEMA_VERSION
from kyc_copilot.contracts.models import Chunk, Document, ParsedFile, Policy, Source

TABLES = ("tool_evidence", "chunks", "documents", "policies", "sources", "meta")
INGESTED_KINDS = ("policy", "procedure", "document")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources(
  source_id TEXT PRIMARY KEY,
  kind      TEXT NOT NULL CHECK(kind IN ('policy','procedure','document','tool')),
  trust     TEXT NOT NULL CHECK(trust IN ('trusted','untrusted')),
  title     TEXT,
  path      TEXT NOT NULL,
  content   TEXT NOT NULL,
  sha256    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS policies(
  source_id         TEXT PRIMARY KEY REFERENCES sources(source_id) ON DELETE CASCADE,
  entity_type       TEXT NOT NULL,
  jurisdiction      TEXT NOT NULL,
  effective_from    TEXT NOT NULL,
  effective_through TEXT NOT NULL,
  edd_threshold     NUMERIC NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policy_lookup
  ON policies(entity_type, jurisdiction, effective_from, effective_through);
CREATE TABLE IF NOT EXISTS documents(
  source_id   TEXT PRIMARY KEY REFERENCES sources(source_id) ON DELETE CASCADE,
  case_id     TEXT,
  doc_type    TEXT,
  is_intake   INTEGER NOT NULL DEFAULT 0,
  review_date TEXT,
  entity_ref  TEXT,
  identity_status TEXT,
  filing_jurisdiction TEXT,
  declared_owner TEXT,
  filing_address TEXT,
  holder_name TEXT,
  birth_year INTEGER,
  document_reference TEXT,
  identity_not_supplied INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_documents_case ON documents(case_id);
CREATE TABLE IF NOT EXISTS chunks(
  source_id    TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
  chunk_no     INTEGER NOT NULL,
  start_line   INTEGER NOT NULL,
  start_offset INTEGER NOT NULL,
  end_offset   INTEGER NOT NULL,
  text         TEXT NOT NULL,
  PRIMARY KEY(source_id, chunk_no)
);
CREATE TABLE IF NOT EXISTS tool_evidence(
  source_id TEXT PRIMARY KEY REFERENCES sources(source_id) ON DELETE CASCADE,
  case_id   TEXT NOT NULL,
  tool      TEXT NOT NULL
);
"""


def normalize_dsn(dsn: str) -> str:
    """Add sslmode=require when the host is remote and the DSN did not set sslmode."""
    parsed = urlparse(dsn)
    if "sslmode" in parse_qs(parsed.query):
        return dsn
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1", ""}:
        return dsn
    query = f"{parsed.query}&sslmode=require" if parsed.query else "sslmode=require"
    return urlunparse(parsed._replace(query=query))


def _as_date(value: date | str) -> str:
    """Normalize date or ISO string to YYYY-MM-DD for inclusive policy lookup."""
    return value.isoformat() if isinstance(value, date) else date.fromisoformat(value).isoformat()


class PostgresKnowledgeStore:
    schema_version = SCHEMA_VERSION

    def __init__(self, dsn: str):
        self.dsn = normalize_dsn(dsn)
        self.conn = psycopg.connect(self.dsn, row_factory=dict_row, autocommit=True)
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> PostgresKnowledgeStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _ensure_schema(self) -> None:
        current = None
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'meta'"
            )
            if cur.fetchone():
                cur.execute("SELECT value FROM meta WHERE key = %s", ("schema_version",))
                row = cur.fetchone()
                if row:
                    current = int(row["value"])
        if current != SCHEMA_VERSION:
            with self.conn.cursor() as cur:
                for table in TABLES:
                    cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            with self.conn.cursor() as cur:
                for statement in SCHEMA.split(";"):
                    sql = statement.strip()
                    if sql:
                        cur.execute(sql)
                cur.execute(
                    "INSERT INTO meta(key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    ("schema_version", str(SCHEMA_VERSION)),
                )

    def replace_all(
        self, parsed: Iterable[ParsedFile], meta: dict[str, str]
    ) -> dict[str, list[str]]:
        """Make the store mirror `parsed` exactly, in one transaction (all or nothing)."""
        parsed = list(parsed)
        incoming = {p.source.source_id: p for p in parsed}
        if len(incoming) != len(parsed):
            raise ValueError("duplicate source IDs in input")
        with self.conn.transaction():
            previous = self.conn.execute(
                "SELECT value FROM meta WHERE key = %s", ("manifest_sha256",)
            ).fetchone()
            if previous and previous["value"] != meta.get("manifest_sha256"):
                self.conn.execute("DELETE FROM sources WHERE kind = %s", ("tool",))
            existing = {
                r["source_id"]: r["sha256"]
                for r in self.conn.execute(
                    "SELECT source_id, sha256 FROM sources WHERE kind IN (%s, %s, %s)",
                    INGESTED_KINDS,
                )
            }
            diff: dict[str, list[str]] = {
                "added": [],
                "updated": [],
                "unchanged": [],
                "removed": [],
            }
            for sid in sorted(set(existing) - set(incoming)):
                self.conn.execute("DELETE FROM sources WHERE source_id = %s", (sid,))
                diff["removed"].append(sid)
            for sid in sorted(incoming):
                item = incoming[sid]
                if sid not in existing:
                    diff["added"].append(sid)
                elif existing[sid] != item.source.sha256:
                    diff["updated"].append(sid)
                else:
                    diff["unchanged"].append(sid)
                self._write(item)
            for key, value in meta.items():
                self.conn.execute(
                    "INSERT INTO meta(key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (key, value),
                )
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("ingested_at", datetime.now(UTC).isoformat()),
            )
        return diff

    def _write(self, item: ParsedFile) -> None:
        s = item.source
        self.conn.execute("DELETE FROM sources WHERE source_id = %s", (s.source_id,))
        self.conn.execute(
            "INSERT INTO sources VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (s.source_id, s.kind, s.trust, s.title, s.path, s.content, s.sha256),
        )
        if item.policy:
            p = item.policy
            self.conn.execute(
                "INSERT INTO policies VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    p.source_id,
                    p.entity_type,
                    p.jurisdiction,
                    p.effective_from.isoformat(),
                    p.effective_through.isoformat(),
                    p.edd_threshold,
                ),
            )
        if item.document:
            d = item.document
            self.conn.execute(
                "INSERT INTO documents VALUES "
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    d.source_id,
                    d.case_id,
                    d.doc_type,
                    int(d.is_intake),
                    d.review_date.isoformat() if d.review_date else None,
                    d.entity_ref,
                    d.identity_status,
                    d.filing_jurisdiction,
                    d.declared_owner,
                    d.filing_address,
                    d.holder_name,
                    d.birth_year,
                    d.document_reference,
                    int(d.identity_not_supplied),
                ),
            )
        for c in item.chunks:
            self.conn.execute(
                "INSERT INTO chunks VALUES (%s, %s, %s, %s, %s, %s)",
                (c.source_id, c.chunk_no, c.start_line, c.start_offset, c.end_offset, c.text),
            )

    @staticmethod
    def _source(row: dict) -> Source:
        return Source(
            row["source_id"],
            row["kind"],
            row["trust"],
            row["title"],
            row["path"],
            row["content"],
            row["sha256"],
        )

    def find_policies(
        self, entity_type: str, jurisdiction: str, review_date: date | str
    ) -> list[Policy]:
        day = _as_date(review_date)
        rows = self.conn.execute(
            "SELECT * FROM policies WHERE entity_type = %s AND jurisdiction = %s "
            "AND effective_from <= %s AND %s <= effective_through ORDER BY source_id",
            (entity_type, jurisdiction, day, day),
        ).fetchall()
        return [
            Policy(
                r["source_id"],
                r["entity_type"],
                r["jurisdiction"],
                date.fromisoformat(r["effective_from"]),
                date.fromisoformat(r["effective_through"]),
                r["edd_threshold"],
            )
            for r in rows
        ]

    def get_source(self, source_id: str) -> Source | None:
        row = self.conn.execute(
            "SELECT * FROM sources WHERE source_id = %s", (source_id,)
        ).fetchone()
        return self._source(row) if row else None

    def get_procedure(self, source_id: str) -> Source | None:
        row = self.conn.execute(
            "SELECT * FROM sources WHERE source_id = %s AND kind = %s",
            (source_id, "procedure"),
        ).fetchone()
        return self._source(row) if row else None

    def case_documents(self, case_id: str) -> list[Source]:
        rows = self.conn.execute(
            "SELECT s.* FROM sources s JOIN documents d USING (source_id) "
            "WHERE d.case_id = %s ORDER BY d.is_intake DESC, s.source_id",
            (case_id,),
        ).fetchall()
        return [self._source(r) for r in rows]

    def get_document(self, source_id: str) -> Document | None:
        r = self.conn.execute(
            "SELECT * FROM documents WHERE source_id = %s", (source_id,)
        ).fetchone()
        if not r:
            return None
        return Document(
            r["source_id"],
            r["case_id"],
            r["doc_type"],
            bool(r["is_intake"]),
            date.fromisoformat(r["review_date"]) if r["review_date"] else None,
            r["entity_ref"],
            r["identity_status"],
            r["filing_jurisdiction"],
            r["declared_owner"],
            r["filing_address"],
            r["holder_name"],
            r["birth_year"],
            r["document_reference"],
            bool(r["identity_not_supplied"]),
        )

    def save_tool_evidence(self, case_id: str, tool: str, source_id: str, content: str) -> None:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self.conn.transaction():
            row = self.conn.execute(
                "SELECT kind FROM sources WHERE source_id = %s", (source_id,)
            ).fetchone()
            if row and row["kind"] != "tool":
                raise ValueError(f"{source_id} is already an ingested {row['kind']}")
            self.conn.execute("DELETE FROM sources WHERE source_id = %s", (source_id,))
            self.conn.execute(
                "INSERT INTO sources VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (source_id, "tool", "untrusted", tool, f"api:{case_id}/{tool}", content, digest),
            )
            self.conn.execute(
                "INSERT INTO tool_evidence VALUES (%s, %s, %s)",
                (source_id, case_id, tool),
            )

    def get_chunks(self, source_id: str) -> list[Chunk]:
        rows = self.conn.execute(
            "SELECT * FROM chunks WHERE source_id = %s ORDER BY chunk_no",
            (source_id,),
        ).fetchall()
        return [
            Chunk(
                r["source_id"],
                r["chunk_no"],
                r["start_line"],
                r["start_offset"],
                r["end_offset"],
                r["text"],
            )
            for r in rows
        ]

    def verify_quote(self, source_id: str, quote: str) -> bool:
        if not isinstance(quote, str) or not quote.strip():
            return False
        row = self.conn.execute(
            "SELECT content FROM sources WHERE source_id = %s", (source_id,)
        ).fetchone()
        return bool(row) and quote in row["content"]

    def counts(self) -> dict[str, int]:
        return {
            k: self.conn.execute(q).fetchone()["count"]
            for k, q in {
                "sources": "SELECT COUNT(*) AS count FROM sources WHERE kind != 'tool'",
                "tool_sources": "SELECT COUNT(*) AS count FROM sources WHERE kind = 'tool'",
                "policies": "SELECT COUNT(*) AS count FROM policies",
                "documents": "SELECT COUNT(*) AS count FROM documents",
                "chunks": "SELECT COUNT(*) AS count FROM chunks",
            }.items()
        }
