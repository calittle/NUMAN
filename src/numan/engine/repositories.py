"""Portable file-backed repositories for fast dispatch data."""

from __future__ import annotations

import difflib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class RepositoryFormatError(ValueError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepositoryFormatError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RepositoryFormatError(f"{path} must contain a JSON object")
    return value


class ExactCacheRepository:
    def lookup(self, key: str) -> str | None:
        raise NotImplementedError


class MappingExactCache(ExactCacheRepository):
    def __init__(self, entries: Mapping[str, str]) -> None:
        self._entries = dict(entries)

    def lookup(self, key: str) -> str | None:
        if key in self._entries:
            return self._entries[key]
        for candidate, response in self._entries.items():
            if candidate in key or key in candidate:
                return response
        return None


class JsonExactCache(MappingExactCache):
    def __init__(self, path: str | Path) -> None:
        raw = _read_object(Path(path))
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in raw.items()):
            raise RepositoryFormatError("exact-cache keys and values must be strings")
        super().__init__(raw)


class ResponsePoolRepository:
    def entries(self, name: str) -> tuple[str, ...]:
        raise NotImplementedError

    def match(self, key: str) -> tuple[str, tuple[str, ...]] | None:
        raise NotImplementedError


class MappingResponsePools(ResponsePoolRepository):
    def __init__(self, pools: Mapping[str, Sequence[str]]) -> None:
        self._pools = {name: tuple(values) for name, values in pools.items()}

    def entries(self, name: str) -> tuple[str, ...]:
        return self._pools.get(name, ())

    def match(self, key: str) -> tuple[str, tuple[str, ...]] | None:
        public = [name for name in self._pools if not name.startswith("_")]
        found = key if key in self._pools else None
        if found is None:
            found = next((name for name in self._pools if name in key or key in name), None)
        if found is None:
            matches = difflib.get_close_matches(key, public, n=1, cutoff=0.75)
            found = matches[0] if matches else None
        entries = self.entries(found) if found else ()
        return (found, entries) if found and entries else None


class JsonResponsePools(MappingResponsePools):
    def __init__(self, path: str | Path) -> None:
        raw = _read_object(Path(path))
        pools: dict[str, tuple[str, ...]] = {}
        for name, values in raw.items():
            if isinstance(values, list) and all(isinstance(item, str) for item in values):
                pools[name] = tuple(values)
        super().__init__(pools)
