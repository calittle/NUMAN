"""Nigel-compatible text normalization and drink-query extraction."""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"\s+")
_NON_STABLE_RE = re.compile(r"[^a-z0-9 ]")
_ROUTINE_PUNCT_RE = re.compile(r"[?.!]")

# Ordered like the sed expressions in Nigel's check_drink_cache/check_drink_db.
_DRINK_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r".*what.*in a (.+)",
        r".*what.s a (.+)",
        r".*what is a (.+)",
        r".*what a (.+)",
        r".*how.*make a (.+)",
        r".*tell me about (.+)",
        r".*recipe for (.+)",
        r".*describe (.+)",
    )
)


def collapse_spaces(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def stable_text(text: str) -> str:
    """Nigel's cache key: lowercase ASCII letters/digits/spaces only."""
    return collapse_spaces(_NON_STABLE_RE.sub("", text.casefold()))


def routine_text(text: str) -> str:
    """Nigel routine normalization: lowercase and remove ? . ! only."""
    return collapse_spaces(_ROUTINE_PUNCT_RE.sub("", text.casefold()))


def extract_drink_query(text: str) -> str | None:
    """Extract the drink phrase using Nigel's ordered trigger forms."""
    for pattern in _DRINK_PATTERNS:
        match = pattern.fullmatch(text.strip())
        if match:
            value = collapse_spaces(match.group(1).replace("?", ""))
            return value.casefold() or None
    return None
