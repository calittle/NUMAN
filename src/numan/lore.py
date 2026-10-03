"""Validated, character-aware venue lore loaded from owner-editable JSON."""

from __future__ import annotations

import json
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
                key = stable_text(alias)
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
        return LoreEntry(entry_id, aliases, responses, source)

    async def lookup(self, text: str, character: Character) -> tuple[str, LoreEntry] | None:
        query = stable_text(text)
        matches = [
            (len(alias), entry)
            for alias, entry in self._aliases.items()
            if alias == query or alias in query
        ]
        for _, entry in sorted(matches, reverse=True, key=lambda item: item[0]):
            response = entry.responses.get(character.id) or entry.responses.get("default")
            if response:
                return response, entry
        return None

    def responses(self, character_id: str) -> tuple[str, ...]:
        return tuple(
            response
            for entry in self.entries
            if (response := entry.responses.get(character_id) or entry.responses.get("default"))
        )
