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
DOCUMENT_FIELDS = ("review date", "entity reference", "identity document", "company name")
IDENTITY_FIELDS = ("name", "birth year", "document reference")
KNOWN_DOC_SUFFIXES = frozenset({"INTAKE", "CORPORATE", "IDENTITY"})
NOT_SUPPLIED_MARKERS = ("not supplied", "was not included")
PROSE_COMPANY_RE = re.compile(r"^(.+?) manufactures\b", re.MULTILINE)


class IngestError(ValueError):
    """A source file is malformed or a policy guard failed; nothing from the run is stored."""


def read_exact(path: Path) -> str:
    """Decode without newline translation: citation quotes must match the supplied text."""
    return path.read_bytes().decode("utf-8")


def _fields(content: str, wanted: tuple[str, ...]) -> tuple[dict[str, str], tuple[str, ...]]:
    """Label values. Two different values for one label are a conflict and the field is unset."""
    found: dict[str, str] = {}
    conflicts: list[str] = []
    for line in content.split("\n"):
        match = FIELD_RE.match(line.rstrip("\r"))
        if not match or match.group(1).lower() not in wanted:
            continue
        label, value = match.group(1).lower(), match.group(2)
        if label not in found and label not in conflicts:
            found[label] = value
        elif label in found and found[label] != value:
            conflicts.append(label)
            del found[label]
    return found, tuple(conflicts)


def _unique_capture(
    pattern: re.Pattern[str], content: str, *, keep_period: bool = False
) -> tuple[str | None, bool]:
    """First unique capture, or (None, True) when the pattern matches two different values."""
    found: list[str] = []
    for match in pattern.finditer(content):
        raw = match.group(1).rstrip("\r").strip()
        value = raw if keep_period else _strip_trailing_period(raw)
        if value not in found:
            found.append(value)
    if len(found) > 1:
        return None, True
    return (found[0] if found else None), False


def _iso_date(value: str, label: str, where: str) -> date:
    """Parse YYYY-MM-DD or stop the ingest with a file-scoped error."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise IngestError(f"{where}: {label} is not an ISO date: {value!r}") from exc


def _number(value: str, where: str) -> int | float:
    """Parse EDD threshold as int preferentially, else float; otherwise stop ingest."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError as exc:
        raise IngestError(f"{where}: EDD monthly threshold is not numeric: {value!r}") from exc


def _strip_trailing_period(value: str) -> str:
    """Drop a single trailing period often left by prose-style field lines."""
    return value.rstrip().removesuffix(".").rstrip()


def _label_value(
    pattern: re.Pattern[str], content: str, *, keep_period: bool = False
) -> str | None:
    """Extract the first regex capture for a labeled field, or None if absent."""
    m = pattern.search(content)
    if not m:
        return None
    raw = m.group(1).rstrip("\r").strip()
    return raw if keep_period else _strip_trailing_period(raw)


def _identity_not_supplied(content: str) -> bool:
    """True when identity prose says the document was not supplied or not included."""
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
        meta, conflicts = _fields(content, DOCUMENT_FIELDS)
        case_id, _, doc_suffix = source_id.rpartition("-")
        suffix_upper = doc_suffix.upper()
        if suffix_upper not in KNOWN_DOC_SUFFIXES:
            warnings.append(f"unrecognized_document_suffix:{source_id}")
        doc_type = doc_suffix.lower() or None
        review_unreadable = False
        if "review date" in meta:
            try:
                review_date = date.fromisoformat(meta["review date"])
            except ValueError:
                review_date = None
                review_unreadable = True
        else:
            review_date = None
        identity_meta: dict[str, str] = {}
        if suffix_upper == "IDENTITY":
            identity_meta, identity_conflicts = _fields(content, IDENTITY_FIELDS)
            conflicts = tuple(dict.fromkeys((*conflicts, *identity_conflicts)))
        birth_raw = identity_meta.get("birth year")
        birth_year = int(birth_raw) if birth_raw and birth_raw.isdigit() else None
        not_supplied = suffix_upper == "IDENTITY" and _identity_not_supplied(content)
        filing_jurisdiction, filing_conflict = _unique_capture(FILING_JURISDICTION_RE, content)
        declared_owner, owner_conflict = _unique_capture(DECLARED_OWNER_RE, content)
        filing_address, address_conflict = _unique_capture(
            FILING_ADDRESS_RE, content, keep_period=True
        )
        extra = [
            name
            for name, flagged in (
                ("filing jurisdiction", filing_conflict),
                ("declared owner", owner_conflict),
                ("filing address", address_conflict),
            )
            if flagged
        ]
        conflicts = tuple(dict.fromkeys((*conflicts, *extra)))
        company_name = meta.get("company name")
        if suffix_upper == "CORPORATE":
            prose = PROSE_COMPANY_RE.search(content)
            prose_name = _strip_trailing_period(prose.group(1).strip()) if prose else None
            if "company name" in conflicts:
                company_name = None
            elif company_name and prose_name and company_name != prose_name:
                conflicts = tuple(dict.fromkeys((*conflicts, "company name")))
                company_name = None
            else:
                company_name = company_name or prose_name
        document = Document(
            source_id,
            case_id or None,
            doc_type,
            suffix_upper == "INTAKE",
            review_date,
            meta.get("entity reference"),
            meta.get("identity document"),
            filing_jurisdiction=filing_jurisdiction,
            declared_owner=declared_owner,
            filing_address=filing_address,
            holder_name=None if not_supplied else identity_meta.get("name"),
            birth_year=None if not_supplied else birth_year,
            document_reference=None if not_supplied else identity_meta.get("document reference"),
            identity_not_supplied=not_supplied,
            company_name=company_name,
            label_conflicts=conflicts,
            empty=not content.strip(),
            review_date_unreadable=review_unreadable,
        )
        source = Source(source_id, "document", UNTRUSTED, title, str(path), content, digest)
        return ParsedFile(
            source,
            document=document,
            chunks=tuple(chunk_paragraphs(source_id, content)),
            warnings=tuple(warnings),
        )

    meta, _policy_conflicts = _fields(content, POLICY_FIELDS)
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
