"""Text normalization and drink-query extraction."""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"\s+")
_NON_STABLE_RE = re.compile(r"[^a-z0-9 ]")
_ROUTINE_PUNCT_RE = re.compile(r"[?.!]")
_TRAILING_QUERY_PUNCT_RE = re.compile(r"[?.!,]+$")

# Conservative corrections for common speech-recognition homophones. These
# apply only after a phrase has already matched a drink-query form.
_DRINK_ALIASES = {
    "mai thai": "mai tai",
    "my thai": "mai tai",
    "my tie": "mai tai",
}

# Preserve the established cache and drink-query precedence.
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
    """Build a stable cache key using lowercase ASCII letters/digits/spaces."""
    return collapse_spaces(_NON_STABLE_RE.sub("", text.casefold()))


def routine_text(text: str) -> str:
    """Normalize routine input by lowercasing and removing ? . ! only."""
    return collapse_spaces(_ROUTINE_PUNCT_RE.sub("", text.casefold()))


def extract_drink_query(text: str) -> str | None:
    """Extract a drink phrase using the supported ordered trigger forms."""
    for pattern in _DRINK_PATTERNS:
        match = pattern.fullmatch(text.strip())
        if match:
            value = collapse_spaces(
                _TRAILING_QUERY_PUNCT_RE.sub("", match.group(1).strip())
            ).casefold()
            return _DRINK_ALIASES.get(value, value) or None
    return None
