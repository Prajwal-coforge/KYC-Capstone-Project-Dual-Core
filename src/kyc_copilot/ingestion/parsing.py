"""Pure parsing of policy and case-document Markdown. File read only; no network."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

from kyc_copilot.contracts.models import (
    TRUSTED,
    UNTRUSTED,
    Chunk,
    Document,
    ParsedFile,
    Policy,
    Source,
)

SOURCE_ID_RE = re.compile(r"^Source ID:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
TITLE_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?):[ \t]*(\S.*?)[ \t]*$")
FILING_JURISDICTION_RE = re.compile(r"Filing jurisdiction:\s*([^\n]+)", re.IGNORECASE)
DECLARED_OWNER_RE = re.compile(r"Declared owner:\s*([^\n]+)", re.IGNORECASE)
FILING_ADDRESS_RE = re.compile(r"Registered address in supplied filing:\s*([^\n]+)", re.IGNORECASE)

POLICY_FIELDS = (
    "entity type",
    "jurisdiction",
    "effective from",
    "effective through",
    "edd monthly threshold",
)
DOCUMENT_FIELDS = ("review date", "entity reference", "identity document")
IDENTITY_FIELDS = ("name", "birth year", "document reference")
KNOWN_DOC_SUFFIXES = frozenset({"INTAKE", "CORPORATE", "IDENTITY"})
NOT_SUPPLIED_MARKERS = ("not supplied", "was not included")


class IngestError(ValueError):
    """A source file is malformed or a policy guard failed; nothing from the run is stored."""


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


def _strip_trailing_period(value: str) -> str:
    return value.rstrip().removesuffix(".").rstrip()


def _label_value(
    pattern: re.Pattern[str], content: str, *, keep_period: bool = False
) -> str | None:
    m = pattern.search(content)
    if not m:
        return None
    raw = m.group(1).rstrip("\r").strip()
    return raw if keep_period else _strip_trailing_period(raw)


def _identity_not_supplied(content: str) -> bool:
    lowered = content.casefold()
    return any(marker in lowered for marker in NOT_SUPPLIED_MARKERS)


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
        case_id, _, doc_suffix = source_id.rpartition("-")
        suffix_upper = doc_suffix.upper()
        if suffix_upper not in KNOWN_DOC_SUFFIXES:
            warnings.append(f"unrecognized_document_suffix:{source_id}")
        doc_type = doc_suffix.lower() or None
        review_date = (
            _iso_date(meta["review date"], "Review date", where) if "review date" in meta else None
        )
        identity_meta = _fields(content, IDENTITY_FIELDS) if suffix_upper == "IDENTITY" else {}
        birth_raw = identity_meta.get("birth year")
        birth_year = int(birth_raw) if birth_raw and birth_raw.isdigit() else None
        not_supplied = suffix_upper == "IDENTITY" and _identity_not_supplied(content)
        document = Document(
            source_id,
            case_id or None,
            doc_type,
            suffix_upper == "INTAKE",
            review_date,
            meta.get("entity reference"),
            meta.get("identity document"),
            filing_jurisdiction=_label_value(FILING_JURISDICTION_RE, content),
            declared_owner=_label_value(DECLARED_OWNER_RE, content),
            filing_address=_label_value(FILING_ADDRESS_RE, content, keep_period=True),
            holder_name=None if not_supplied else identity_meta.get("name"),
            birth_year=None if not_supplied else birth_year,
            document_reference=None if not_supplied else identity_meta.get("document reference"),
            identity_not_supplied=not_supplied,
        )
        source = Source(source_id, "document", UNTRUSTED, title, str(path), content, digest)
        return ParsedFile(
            source,
            document=document,
            chunks=tuple(chunk_paragraphs(source_id, content)),
            warnings=tuple(warnings),
        )

    meta = _fields(content, POLICY_FIELDS)
    if not meta:  # e.g. KYC-SCOPE-01: a procedure that applies to every case
        source = Source(source_id, "procedure", TRUSTED, title, str(path), content, digest)
        return ParsedFile(
            source,
            chunks=tuple(chunk_paragraphs(source_id, content)),
            warnings=tuple(warnings),
        )
    missing = [f for f in POLICY_FIELDS if f not in meta]
    if missing:
        raise IngestError(f"{where}: policy is missing {', '.join(missing)}")
    effective_from = _iso_date(meta["effective from"], "Effective from", where)
    effective_through = _iso_date(meta["effective through"], "Effective through", where)
    if effective_from > effective_through:
        raise IngestError(f"{where}: effective window is reversed")
    policy = Policy(
        source_id,
        meta["entity type"],
        meta["jurisdiction"],
        effective_from,
        effective_through,
        _number(meta["edd monthly threshold"], where),
    )
    source = Source(source_id, "policy", TRUSTED, title, str(path), content, digest)
    return ParsedFile(
        source,
        policy=policy,
        chunks=tuple(chunk_paragraphs(source_id, content)),
        warnings=tuple(warnings),
    )
