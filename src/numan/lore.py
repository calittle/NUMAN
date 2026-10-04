"""Validated, character-aware venue lore loaded from owner-editable JSON."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .engine.models import Character
from .engine.normalization import stable_text


class LoreFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LoreEntry:
    id: str
    aliases: tuple[str, ...]
    responses: dict[str, str]
    source: str
    topics: tuple[str, ...] = ()


class JsonLoreProvider:
    def __init__(self, path: str | Path) -> None:
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise TypeError("top level must be a list")
            entries = tuple(self._parse(item) for item in raw)
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise LoreFormatError(f"cannot load venue lore from {source}: {exc}") from exc
        self.entries = entries
        ids = [entry.id for entry in entries]
        if len(ids) != len(set(ids)):
            raise LoreFormatError("duplicate lore id")
        self._aliases: dict[str, LoreEntry] = {}
        for entry in entries:
            for alias in entry.aliases:
                key = self._key(alias)
                if not key:
                    raise LoreFormatError(f"lore {entry.id!r} has an empty alias")
                if key in self._aliases:
                    raise LoreFormatError(f"duplicate lore alias: {alias}")
                self._aliases[key] = entry

    @staticmethod
    def _parse(raw) -> LoreEntry:
        entry_id = str(raw["id"]).strip()
        aliases = tuple(str(value).strip() for value in raw["aliases"])
        responses = {
            str(key): str(value).strip() for key, value in raw["responses"].items()
        }
        source = str(raw["source"]).strip()
        if not entry_id or not aliases or not responses or not source:
            raise LoreFormatError("lore requires id, aliases, responses, and source")
        if any(not value for value in responses.values()):
            raise LoreFormatError(f"lore {entry_id!r} has an empty response")
        return LoreEntry(entry_id, aliases, responses, source,
                         tuple(str(value).strip() for value in raw.get("topics", ())))

    @staticmethod
    def _key(text: str) -> str:
        return stable_text("".join(c for c in unicodedata.normalize("NFKD", text)
                                   if not unicodedata.combining(c)))

    def related_entries(self, text: str) -> tuple[LoreEntry, ...]:
        query = self._key(text)
        matches = []
        for entry in self.entries:
            lengths = [len(self._key(topic)) for topic in entry.topics
                       if self._key(topic) and re.search(
                           rf"\b{re.escape(self._key(topic))}s?\b", query)]
            if lengths:
                matches.append((max(lengths), entry))
        return tuple(entry for _, entry in sorted(
            matches, key=lambda item: item[0], reverse=True))

    def is_related(self, text: str) -> bool:
        query = self._key(text)
        return bool(self.related_entries(text)) or any(
            re.search(rf"\b{re.escape(alias)}\b", query) for alias in self._aliases)

    def unknown(self, character: Character) -> tuple[str, LoreEntry]:
        entry = next(item for item in self.entries if item.id == "unknown_lore")
        return entry.responses.get(character.id) or entry.responses["default"], entry

    async def lookup(self, text: str, character: Character) -> tuple[str, LoreEntry] | None:
        query = self._key(text)
        matches = [
            (len(alias), entry)
            for alias, entry in self._aliases.items()
            if re.search(rf"\b{re.escape(alias)}\b", query)
        ]
        for _, entry in sorted(matches, reverse=True, key=lambda item: item[0]):
            response = entry.responses.get(character.id) or entry.responses.get("default")
            if response:
                return response, entry
        related = self.related_entries(text)
        if related:
            subjects = [entry for entry in related if entry.id != "unknown_lore"]
            if len(subjects) == 1:
                entry = subjects[0]
                response = entry.responses.get(character.id) or entry.responses.get("default")
                if response:
                    return response, entry
            return self.unknown(character)
        return None

    def responses(self, character_id: str) -> tuple[str, ...]:
        return tuple(
            response
            for entry in self.entries
            if (response := entry.responses.get(character_id) or entry.responses.get("default"))
        )
