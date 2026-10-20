"""Pure parsing of policy and case-document Markdown files. No I/O except reading a file."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .models import TRUSTED, UNTRUSTED, Chunk, Document, Policy, Source

SOURCE_ID_RE = re.compile(r"^Source ID:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
TITLE_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?):[ \t]*(\S.*?)[ \t]*$")

POLICY_FIELDS = ("entity type", "jurisdiction", "effective from", "effective through",
                 "edd monthly threshold")
DOCUMENT_FIELDS = ("review date", "entity reference")


class IngestError(ValueError):
    """A source file is malformed; nothing from the run is stored."""


@dataclass
class ParsedFile:
    source: Source
    policy: Policy | None = None
    document: Document | None = None
    chunks: list[Chunk] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def read_exact(path: Path) -> str:
    """Decode without newline translation: citation quotes must match the supplied text."""
    return path.read_bytes().decode("utf-8")


def _fields(content: str, wanted: tuple[str, ...]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in content.split("\n"):
        m = FIELD_RE.match(line.rstrip("\r"))
        if m and m.group(1).lower() in wanted and m.group(1).lower() not in found:
            found[m.group(1).lower()] = m.group(2)
    return found


def _iso_date(value: str, label: str, where: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise IngestError(f"{where}: {label} is not an ISO date: {value!r}") from exc


def _number(value: str, where: str) -> int | float:
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError as exc:
        raise IngestError(f"{where}: EDD monthly threshold is not numeric: {value!r}") from exc


def chunk_paragraphs(source_id: str, content: str) -> list[Chunk]:
    """Blank-line separated paragraphs; chunk.text == content[start_offset:end_offset]."""
    chunks: list[Chunk] = []
    start = end = None
    start_line = 0
    offset = 0
    for line_no, raw in enumerate(content.split("\n"), start=1):
        line_end = offset + len(raw)
        if raw.strip():
            if start is None:
                start, start_line = offset, line_no
            end = line_end - (1 if raw.endswith("\r") else 0)
        elif start is not None:
            chunks.append(Chunk(source_id, len(chunks), start_line, start, end, content[start:end]))
            start = end = None
        offset = line_end + 1
    if start is not None:
        chunks.append(Chunk(source_id, len(chunks), start_line, start, end, content[start:end]))
    return chunks


def parse_file(path: Path, folder: str) -> ParsedFile:
    """folder is 'policies' or 'documents'."""
    where = path.name
    content = read_exact(path)
    warnings: list[str] = []

    m = SOURCE_ID_RE.search(content)
    if m:
        source_id = m.group(1)
        if source_id != path.stem:
            warnings.append(f"{where}: header Source ID {source_id!r} differs from filename")
    else:
        source_id = path.stem
        warnings.append(f"{where}: no 'Source ID:' header; using filename")
    title_match = TITLE_RE.search(content)
    title = title_match.group(1) if title_match else None
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    if folder == "documents":
        meta = _fields(content, DOCUMENT_FIELDS)
        case_id, _, doc_type = source_id.rpartition("-")
        review_date = (_iso_date(meta["review date"], "Review date", where)
                       if "review date" in meta else None)
        document = Document(source_id, case_id or None, doc_type.lower() or None,
                            doc_type.upper() == "INTAKE", review_date, meta.get("entity reference"))
        source = Source(source_id, "document", UNTRUSTED, title, str(path), content, digest)
        return ParsedFile(source, document=document, chunks=chunk_paragraphs(source_id, content),
                          warnings=warnings)

    meta = _fields(content, POLICY_FIELDS)
    if not meta:  # e.g. KYC-SCOPE-01: a procedure that applies to every case
        source = Source(source_id, "procedure", TRUSTED, title, str(path), content, digest)
        return ParsedFile(source, chunks=chunk_paragraphs(source_id, content), warnings=warnings)
    missing = [f for f in POLICY_FIELDS if f not in meta]
    if missing:
        raise IngestError(f"{where}: policy is missing {', '.join(missing)}")
    effective_from = _iso_date(meta["effective from"], "Effective from", where)
    effective_through = _iso_date(meta["effective through"], "Effective through", where)
    if effective_from > effective_through:
        raise IngestError(f"{where}: effective window is reversed")
    policy = Policy(source_id, meta["entity type"], meta["jurisdiction"], effective_from,
                    effective_through, _number(meta["edd monthly threshold"], where))
    source = Source(source_id, "policy", TRUSTED, title, str(path), content, digest)
    return ParsedFile(source, policy=policy, chunks=chunk_paragraphs(source_id, content),
                      warnings=warnings)
