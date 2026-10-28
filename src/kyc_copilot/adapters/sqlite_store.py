"""SQLite adapter for the KnowledgeStore port (standard library only).

This database belongs to the application. It is separate from the mock service's
`.state/mock.sqlite`, which the application must never open or modify.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from kyc_copilot.contracts.models import Chunk, Document, ParsedFile, Policy, Source

# Bump when the schema changes. Everything stored is derived (re-ingested or re-fetched), so an
# older database is simply rebuilt.
SCHEMA_VERSION = 4
TABLES = ("tool_evidence", "chunks", "documents", "policies", "sources", "meta")
INGESTED_KINDS = ("policy", "procedure", "document")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
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
  identity_not_supplied INTEGER NOT NULL DEFAULT 0,
  company_name TEXT,
  label_conflicts TEXT NOT NULL DEFAULT '[]',
  empty INTEGER NOT NULL DEFAULT 0,
  review_date_unreadable INTEGER NOT NULL DEFAULT 0
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


def _as_date(value: date | str) -> str:
    """Normalize date or ISO string to YYYY-MM-DD for SQLite comparisons."""
    return value.isoformat() if isinstance(value, date) else date.fromisoformat(value).isoformat()


class SqliteKnowledgeStore:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: we issue BEGIN/COMMIT ourselves for explicit transactions.
        self.db = sqlite3.connect(str(path), timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self.db.execute("PRAGMA journal_mode = WAL")
        if self.db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            for table in TABLES:
                self.db.execute(f"DROP TABLE IF EXISTS {table}")
            self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> SqliteKnowledgeStore:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ---- writes -------------------------------------------------------------------

    def replace_all(
        self, parsed: Iterable[ParsedFile], meta: dict[str, str]
    ) -> dict[str, list[str]]:
        """Make the store mirror `parsed` exactly, in one transaction (all or nothing).

        Re-running with identical input changes nothing. Sources no longer supplied are
        removed, so a fresh fixture set never mixes with stale policy or case text.
        """
        parsed = list(parsed)
        incoming = {p.source.source_id: p for p in parsed}
        if len(incoming) != len(parsed):
            raise ValueError("duplicate source IDs in input")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.db.execute(
                "SELECT value FROM meta WHERE key='manifest_sha256'"
            ).fetchone()
            if previous and previous["value"] != meta.get("manifest_sha256"):
                # A different fixture set: tool evidence fetched for the old one is stale.
                self.db.execute("DELETE FROM sources WHERE kind='tool'")
            existing = {
                r["source_id"]: r["sha256"]
                for r in self.db.execute(
                    "SELECT source_id, sha256 FROM sources WHERE kind IN (?,?,?)",
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
                self.db.execute("DELETE FROM sources WHERE source_id=?", (sid,))
                diff["removed"].append(sid)
            for sid in sorted(incoming):
                item = incoming[sid]
                if sid not in existing:
                    diff["added"].append(sid)
                elif existing[sid] != item.source.sha256:
                    diff["updated"].append(sid)
                else:
                    diff["unchanged"].append(sid)
                self._write(item)  # always rewrite derived rows (links may have changed)
            for key, value in meta.items():
                self.db.execute(
                    "INSERT INTO meta(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )
            self.db.execute(
                "INSERT INTO meta(key,value) VALUES('ingested_at',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (datetime.now(UTC).isoformat(),),
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return diff

    def _write(self, item: ParsedFile) -> None:
        """Replace one source and its policy/document/chunk rows (delete then insert)."""
        s = item.source
        self.db.execute("DELETE FROM sources WHERE source_id=?", (s.source_id,))
        self.db.execute(
            "INSERT INTO sources VALUES(?,?,?,?,?,?,?)",
            (s.source_id, s.kind, s.trust, s.title, s.path, s.content, s.sha256),
        )
        if item.policy:
            p = item.policy
            self.db.execute(
                "INSERT INTO policies VALUES(?,?,?,?,?,?)",
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
            self.db.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    d.company_name,
                    json.dumps(list(d.label_conflicts)),
                    int(d.empty),
                    int(d.review_date_unreadable),
                ),
            )
        self.db.executemany(
            "INSERT INTO chunks VALUES(?,?,?,?,?,?)",
            [
                (c.source_id, c.chunk_no, c.start_line, c.start_offset, c.end_offset, c.text)
                for c in item.chunks
            ],
        )

    # ---- reads (the KnowledgeStore port) ------------------------------------------

    @staticmethod
    def _source(row: sqlite3.Row) -> Source:
        """Map a sources table row into the frozen Source contract."""
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
        """Policies effective on review_date for the entity/jurisdiction pair."""
        day = _as_date(review_date)
        rows = self.db.execute(
            "SELECT * FROM policies WHERE entity_type=? AND jurisdiction=? "
            "AND effective_from<=? AND ?<=effective_through ORDER BY source_id",
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

    def all_policies(self) -> list[Policy]:
        """Every stored product policy, ordered by source_id."""
        rows = self.db.execute("SELECT * FROM policies ORDER BY source_id").fetchall()
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
        """Return any stored source by id, or None if unknown."""
        row = self.db.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
        return self._source(row) if row else None

    def get_procedure(self, source_id: str) -> Source | None:
        """Return a procedure/scope source only; None when missing or wrong kind."""
        row = self.db.execute(
            "SELECT * FROM sources WHERE source_id=? AND kind='procedure'",
            (source_id,),
        ).fetchone()
        return self._source(row) if row else None

    def case_documents(self, case_id: str) -> list[Source]:
        """Documents linked to the case, intake first then by source_id."""
        rows = self.db.execute(
            "SELECT s.* FROM sources s JOIN documents d USING(source_id) "
            "WHERE d.case_id=? ORDER BY d.is_intake DESC, s.source_id",
            (case_id,),
        ).fetchall()
        return [self._source(r) for r in rows]

    def get_document(self, source_id: str) -> Document | None:
        """Parsed document metadata for a source, or None if not a document."""
        r = self.db.execute("SELECT * FROM documents WHERE source_id=?", (source_id,)).fetchone()
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
            r["company_name"],
            tuple(json.loads(r["label_conflicts"] or "[]")),
            bool(r["empty"]),
            bool(r["review_date_unreadable"]),
        )

    def save_tool_evidence(self, case_id: str, tool: str, source_id: str, content: str) -> None:
        """Store a tool response as an untrusted source so citations to it can be verified.

        `content` must already be redacted; restricted values are never written to disk.
        """
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT kind FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()
            if row and row["kind"] != "tool":
                raise ValueError(f"{source_id} is already an ingested {row['kind']}")
            self.db.execute("DELETE FROM sources WHERE source_id=?", (source_id,))
            self.db.execute(
                "INSERT INTO sources VALUES(?,?,?,?,?,?,?)",
                (source_id, "tool", "untrusted", tool, f"api:{case_id}/{tool}", content, digest),
            )
            self.db.execute("INSERT INTO tool_evidence VALUES(?,?,?)", (source_id, case_id, tool))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def get_chunks(self, source_id: str) -> list[Chunk]:
        """Paragraph chunks in order for citation and retrieval."""
        rows = self.db.execute(
            "SELECT * FROM chunks WHERE source_id=? ORDER BY chunk_no", (source_id,)
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
        """True only if quote is non-blank and an exact substring of the source text."""
        if not isinstance(quote, str) or not quote.strip():
            return False
        row = self.db.execute(
            "SELECT content FROM sources WHERE source_id=?", (source_id,)
        ).fetchone()
        return bool(row) and quote in row["content"]

    def counts(self) -> dict[str, int]:
        """Row totals for ingest summaries; ingested sources exclude tool evidence."""
        return {
            k: self.db.execute(q).fetchone()[0]
            for k, q in {
                "sources": "SELECT COUNT(*) FROM sources WHERE kind != 'tool'",
                "tool_sources": "SELECT COUNT(*) FROM sources WHERE kind = 'tool'",
                "policies": "SELECT COUNT(*) FROM policies",
                "documents": "SELECT COUNT(*) FROM documents",
                "chunks": "SELECT COUNT(*) FROM chunks",
            }.items()
        }
