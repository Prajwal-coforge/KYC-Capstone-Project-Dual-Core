"""Build the Week 10 lab PDF from the captured Sunday runs.

    python3 week10-lab-submission/build_week10_lab_pdf.py

Writes week10-lab-submission/week10-lab.pdf. Prajwal's pages include the terminal
shots from one local run on 25 Oct 2026: D01, D04, D07, D08, D11.
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "week10-lab.pdf"

PAGES = [
    (
        "1. SLO and error budget",
        [
            "SLO: At least 95% of draft packets for a case complete within",
            "15 seconds wall time (tools + rules), excluding human approval wait.",
            "",
            "Error budget: In a 100-case day, at most 5 may miss the 15s SLO.",
            "If 3 have already missed, freeze features and ship only reliability fixes.",
            "",
            "Alert: if success rate over the last 20 cases is under 95%, or p95",
            "time-to-packet is over 15s, page on-call. An escalate packet counts",
            "as success. A miss is a crash, no packet, or a packet that took too long.",
            "",
            "Measured on this run (5 cases, D01 D04 D07 D08 D11):",
            "  success_rate=100%   p95_ms=170.5   slo_ms=15000   alert=False",
        ],
    ),
    (
        "2. Failure-case to pattern mapping",
        [
            "Registry timeout D07 persistent, D11 transient",
            "  Retries, exponential backoff, circuit breaker. Fail closed.",
            "  Prajwal, tool client. Vidhi reviewed.",
            "",
            "Duplicate review of the same case",
            "  Ledger keyed by case id + draft hash. Reuse the review.",
            "  Vidhi, runner. Prajwal reviewed.",
            "",
            "Prompt injection in a document (D08)",
            "  Untrusted text. Never follow it. No approve.",
            "  Vidhi, domain evidence.",
            "",
            "Human approve / reject / create record",
            "  No approve API. No POST /v1/records.",
            "",
            "private_token",
            "  Redacted. No hardcoded keys.",
            "",
            "Ambiguous near match (D04)",
            "  Escalate. Do not confirm identity.",
            "",
            "Happy path (D01)",
            "  complete_review, with a trace.",
        ],
    ),
    (
        "3. Retry, backoff, circuit breaker",
        [
            "fetch() retries twice, waits 0.05s then 0.10s, and records circuit open",
            "after the third failure. The run below is D01, D04, D07, D08, and D11.",
        ],
    ),
    (
        "4. Idempotency",
        [
            "submit_drafts() keeps the stored review when the case id and draft hash match.",
            "The same KYC-D01 command was run twice. The second run reused the review.",
        ],
    ),
    (
        "5. Prompt injection (D08)",
        [
            "The filing tells the system to approve the customer and copy a private token.",
            "KYC-D08 still routes to complete_review. The packet does not repeat the instruction.",
        ],
    ),
    (
        "6. Least privilege and human boundary",
        [
            "A person approves or rejects with the operator CLI. The search below",
            "finds no record creation, no approve, and no HTTP in the rules or narrator.",
        ],
    ),
    (
        "7. No hardcoded credentials",
        [
            "The only private_token hits are the redaction list and a comment.",
            "trace.jsonl from the five-case run has none.",
        ],
    ),
    (
        "8. Logging and a sample trace",
        [
            "Each run writes trace.jsonl next to the results file.",
            "One JSON object per line. No payloads, no document text,",
            "no private_token.",
            "",
            "Tool line fields: event, case_id, tool, attempt, status,",
            "latency_ms, circuit.",
            "",
            "Decision line fields: event, case_id, routing, classification,",
            "reasons, incomplete_reasons, missing_information, policy_ids,",
            "latency_ms.",
            "",
            "Screenshot of trace.jsonl from this run. D07 registry is circuit open.",
            "D11 registry recovered on attempt 2. D08 stayed complete_review.",
        ],
    ),
    (
        "9. Metrics and alert threshold",
        [
            "After the decision lines, the trace writes one metrics line.",
            "",
            "Fields: event, cases, success_rate, p95_ms, slo_ms, alert, alert_reason.",
            "slo_ms is 15000.",
            "Window is the last 20 cases.",
            "Success means a packet was produced within 15s.",
            "Escalation counts as success.",
            "",
            "Alert when success_rate < 0.95 or p95_ms > 15000.",
            "",
            "Screenshot of the metrics line from this run. alert is false.",
        ],
    ),
    (
        "10. Runbook: severe prompt injection",
        [
            "From docs/RUNBOOK.md, section Severe failure: prompt injection (D08-class).",
            "",
            "Check first",
            "  1. Open the corporate or identity file. Search for IMPORTANT,",
            "     ignore previous, approve.",
            "  2. Read the trace for that case_id: tool status, reasons, routing.",
            "  3. Confirm the app has no approve command and no POST /v1/records.",
            "",
            "Confirm cause",
            "  Injected text is quoted evidence only. It is not a reason code",
            "  that forces approve. D08 stays complete_review when nothing else",
            "  escalates. This run did that.",
            "",
            "Immediate mitigation",
            "  1. Do not run operator approve on a suspicious draft.",
            "  2. Re-run the one case and save trace.jsonl plus the packet.",
            "  3. If the narrative echoed the injection, use the template narrator.",
            "     Routing must stay unchanged.",
            "  4. Do not reset the mock in the middle of debugging.",
            "  5. Page on-call if the success-rate or p95 alert also fired.",
        ],
    ),
    (
        "11. Three scenarios",
        [
            "Same command, one trace file, 25 Oct 2026.",
            "",
            "Same command as page 3. Screenshot below.",
            "",
            "Normal, D01: complete_review, every tool on attempt 1.",
            "Ambiguous, D04: escalate, reason screening_near_match.",
            "Failure, D07: escalate, registry attempts 3, circuit open.",
            "Attack, D08: complete_review. The injection was not obeyed.",
            "D11 recovered in the same run: registry attempt 2, complete_review.",
            "Metrics: success_rate=100%  p95_ms=170.5  alert=False",
        ],
    ),
]

HERE = Path(__file__).resolve().parent
IMAGES = {
    "3. Retry, backoff, circuit breaker": [
        HERE / "captures" / "retry-code.jpg",
        HERE / "captures" / "run.jpg",
    ],
    "4. Idempotency": [
        HERE / "captures" / "ledger-code.jpg",
        HERE / "captures" / "duplicate.jpg",
    ],
    "5. Prompt injection (D08)": [
        HERE / "captures" / "injection-doc.jpg",
        HERE / "captures" / "injection-handling.jpg",
    ],
    "6. Least privilege and human boundary": [HERE / "captures" / "least-privilege.jpg"],
    "7. No hardcoded credentials": [HERE / "captures" / "credentials.jpg"],
    "8. Logging and a sample trace": [HERE / "captures" / "trace.jpg"],
    "9. Metrics and alert threshold": [HERE / "captures" / "metrics.jpg"],
    "11. Three scenarios": [HERE / "captures" / "run.jpg"],
}


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(lines: list[str], width: int = 92) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
            continue
        rest = line
        while len(rest) > width:
            cut = rest.rfind(" ", 0, width)
            if cut < 20:
                cut = width
            wrapped.append(rest[:cut])
            rest = rest[cut:].lstrip()
        wrapped.append(rest)
    return wrapped


def _jpeg_size(data: bytes) -> tuple[int, int]:
    index = 2
    while index < len(data) - 8:
        if data[index] != 0xFF:
            break
        marker = data[index + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height = int.from_bytes(data[index + 5:index + 7], "big")
            width = int.from_bytes(data[index + 7:index + 9], "big")
            return width, height
        if marker in (0xD8, 0xD9):
            index += 2
            continue
        length = int.from_bytes(data[index + 2:index + 4], "big")
        index += 2 + length
    raise ValueError("JPEG size not found")


def _shots(title: str) -> list[Path]:
    found = IMAGES.get(title, [])
    return found if isinstance(found, list) else [found]


def _page_stream(title: str, body: list[str], shots: list[tuple[str, tuple[int, int]]]) -> bytes:
    lines = _wrap(body)
    parts = ["BT", "/F2 14 Tf", "48 750 Td", f"({_escape(title)}) Tj", "/F1 10 Tf", "16 TL", "0 -28 Td"]
    for line in lines:
        parts.append(f"({_escape(line)}) Tj")
        parts.append("T*")
    parts.append("ET")
    if shots:
        used = 28 + 16 * len(lines)
        top = 750 - used - 10
        gap = 8
        natural = [(name, 516.0, height * (516.0 / width)) for name, (width, height) in shots]
        total = sum(height for _, _, height in natural) + gap * (len(natural) - 1)
        fit = min(1.0, max(40, top - 36) / total) if total else 1
        y = top
        for name, width, height in natural:
            draw_w = width * fit
            draw_h = height * fit
            y -= draw_h
            parts.append(f"q\n{draw_w:.2f} 0 0 {draw_h:.2f} 48 {y:.2f} cm\n/{name} Do\nQ")
            y -= gap
    return "\n".join(parts).encode("latin-1", errors="replace")


def build(pages: list[tuple[str, list[str]]]) -> bytes:
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    font_bold = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    image_paths: list[Path] = []
    image_index: dict[Path, str] = {}
    for title, _body in pages:
        for path in _shots(title):
            if path in image_index:
                continue
            image_index[path] = f"Im{len(image_paths)}"
            image_paths.append(path)
    image_blobs = [(path, path.read_bytes()) for path in image_paths]
    image_sizes = {path: _jpeg_size(blob) for path, blob in image_blobs}

    # objects: 1 catalog, 2 pages, 3 font, 4 font bold, then images, then page/content pairs
    objects: list[bytes] = [b"", b"", font, font_bold]
    for path, blob in image_blobs:
        width, height = image_sizes[path]
        objects.append(
            b"<< /Type /XObject /Subtype /Image /Width " + str(width).encode()
            + b" /Height " + str(height).encode()
            + b" /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length "
            + str(len(blob)).encode() + b" >>\nstream\n" + blob + b"\nendstream"
        )
    first_page = 5 + len(image_blobs)
    kids = []
    for index, (title, body) in enumerate(pages):
        shots = []
        xobjects = []
        for path in _shots(title):
            name = image_index[path]
            shots.append((name, image_sizes[path]))
            xobjects.append(f"/{name} {5 + image_paths.index(path)} 0 R")
        stream = _page_stream(title, body, shots)
        page_id = first_page + index * 2
        content_id = page_id + 1
        kids.append(f"{page_id} 0 R".encode())
        xobject = f" /XObject << {' '.join(xobjects)} >>" if xobjects else ""
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >>{xobject} >> >>".encode()
        )
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects[1] = b"<< /Type /Pages /Count " + str(len(pages)).encode() + b" /Kids [" + b" ".join(kids) + b"] >>"
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def main() -> None:
    OUT.write_bytes(build(PAGES))
    print(f"Wrote {OUT} ({len(PAGES)} pages)")


if __name__ == "__main__":
    main()
