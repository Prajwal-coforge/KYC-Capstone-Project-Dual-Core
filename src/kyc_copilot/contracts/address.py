"""Address helpers for layers that may import contracts only (e.g. narrative).

Decision-path Strategy lives in `kyc_copilot.domain.rules.TokenMapAddressCanonicalizer`.
This module mirrors the same Tier-1 token map so narrative stays contracts-only.
"""

from __future__ import annotations

import re
import unicodedata
from types import MappingProxyType

from kyc_copilot.contracts.interfaces import AddressCanonicalizer

_ADDRESS_TOKEN_MAP = MappingProxyType(
    {
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
)


class _TokenMapCanonicalizer:
    def canonicalize(self, raw_address: str) -> str:
        text = unicodedata.normalize("NFKC", raw_address).casefold()
        words = re.sub(r"[^\w\s]", " ", text).split()
        return " ".join(_ADDRESS_TOKEN_MAP.get(w, w) for w in words)


_DEFAULT: AddressCanonicalizer = _TokenMapCanonicalizer()


def normalize_address(text: str, canonicalizer: AddressCanonicalizer = _DEFAULT) -> str:
    return canonicalizer.canonicalize(text)


def compare_addresses(
    a: str | None,
    b: str | None,
    canonicalizer: AddressCanonicalizer = _DEFAULT,
) -> str:
    if not isinstance(a, str) or not isinstance(b, str) or not a.strip() or not b.strip():
        return "unknown"
    if a == b:
        return "same"
    left = canonicalizer.canonicalize(a)
    right = canonicalizer.canonicalize(b)
    return "normalized_same" if left == right else "different"
