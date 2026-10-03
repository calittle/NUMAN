"""Text normalization and drink-query extraction."""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"\s+")
_NON_STABLE_RE = re.compile(r"[^a-z0-9 ]")
_ROUTINE_PUNCT_RE = re.compile(r"[?.!]")
_TRAILING_QUERY_PUNCT_RE = re.compile(r"[?,]+$")
_KRAKEN_HOMOPHONE_RE = re.compile(r"\b(?:crackin|cracking|cracken)\b")
_KRAKEN_CURSE_RE = re.compile(r"\bkraken curse\b")

# Conservative corrections for common speech-recognition homophones. These
# apply only after a phrase has already matched a drink-query form.
_DRINK_ALIASES = {
    "mai thai": "mai tai",
    "my thai": "mai tai",
    "my tie": "mai tai",
}

_DRINK_QUERY_FORMS = (
    re.compile(r"\b(?:make|mix|build)(?:\s+me)?\s+(?:a|an|the)\s+(?P<drink>.+)$"),
    re.compile(r"\bi(?: would|'d)?\s+like\s+(?:a|an|the)\s+(?P<drink>.+)$"),
    re.compile(r"\bwhat(?:'s| is)?\s+in\s+a\s+(?P<drink>.+)$"),
    re.compile(r"\bwhat(?:'s|s| is)\s+a\s+(?P<drink>.+)$"),
    re.compile(r"\bwhat\s+a\s+(?P<drink>.+)$"),
    re.compile(r"\bhow\b.*\bmake\s+a\s+(?P<drink>.+)$"),
    re.compile(r"\btell\s+me\s+about\s+(?P<drink>.+)$"),
    re.compile(r"\brecipe\s+for\s+(?P<drink>.+)$"),
    re.compile(r"\bdescribe\s+(?P<drink>.+)$"),
)


def collapse_spaces(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def stable_text(text: str) -> str:
    """Build a stable cache key using lowercase ASCII letters/digits/spaces."""
    normalized = collapse_spaces(_NON_STABLE_RE.sub("", text.casefold()))
    # Whisper often renders the venue's short-a pronunciation of Kraken as
    # "crackin'". Correct that homophone only in stable matching keys; the raw
    # transcript remains available for logs and display.
    normalized = _KRAKEN_HOMOPHONE_RE.sub("kraken", normalized)
    return _KRAKEN_CURSE_RE.sub("krakens curse", normalized)


def routine_text(text: str) -> str:
    """Normalize routine input by lowercasing and removing ? . ! only."""
    return collapse_spaces(_ROUTINE_PUNCT_RE.sub("", text.casefold()))


def extract_drink_query(text: str) -> str | None:
    """Extract a drink phrase using the supported ordered trigger forms."""
    normalized = routine_text(text)
    for form in _DRINK_QUERY_FORMS:
        match = form.search(normalized)
        if match:
            value = _TRAILING_QUERY_PUNCT_RE.sub("", match.group("drink")).strip()
            return _DRINK_ALIASES.get(value, value) or None
    return None
