"""US address normalization helpers. Stdlib only; no I/O."""

from __future__ import annotations

import re

# US street suffixes and directionals (ASSUMPTIONS.md 3.1). Anything else is compared literally,
# so an unrecognized abbreviation counts as a material difference.
_ABBREVIATIONS = {
    "st": "street",
    "ave": "avenue",
    "av": "avenue",
    "rd": "road",
    "blvd": "boulevard",
    "dr": "drive",
    "ln": "lane",
    "ct": "court",
    "pl": "place",
    "sq": "square",
    "ter": "terrace",
    "pkwy": "parkway",
    "hwy": "highway",
    "cir": "circle",
    "ste": "suite",
    "apt": "apartment",
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
}


def normalize_address(text: str) -> str:
    words = re.sub(r"[^\w\s]", " ", text.casefold()).split()
    return " ".join(_ABBREVIATIONS.get(w, w) for w in words)


def compare_addresses(a: str | None, b: str | None) -> str:
    if not isinstance(a, str) or not isinstance(b, str) or not a.strip() or not b.strip():
        return "unknown"
    if a == b:
        return "same"
    return "normalized_same" if normalize_address(a) == normalize_address(b) else "different"
