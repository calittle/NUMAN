"""Enumerate and pre-render deterministic speech before show time."""

from __future__ import annotations

import json
from pathlib import Path

from .performance import GROG_STALLING_PLAN, POLLY_STALLING_PLAN
from .recipes import JsonCocktailProvider
from .show_control import DrinkPresentationCatalog
from .voice import VoiceProvider


def deterministic_responses(project_root: Path) -> dict[str, tuple[str, ...]]:
    recipes = JsonCocktailProvider(project_root / "data/cocktails/recipes.json").responses()
    presentations = DrinkPresentationCatalog(
        project_root / "data/show/drink_presentations.json"
    )
    stalling = {"grog": GROG_STALLING_PLAN, "polly": POLLY_STALLING_PLAN}
    results = {}
    for character_id in stalling:
        values = set(recipes)
        values.update(_object_values(project_root / f"data/{character_id}/exact_cache.json"))
        values.update(_pool_values(project_root / f"data/{character_id}/response_pools.json"))
        for presentation in presentations.items:
            values.update(presentation.responses.get(character_id, ()))
        plan = stalling[character_id]
        values.update(plan.fillers)
        values.add(plan.transition)
        results[character_id] = tuple(sorted(value for value in values if value.strip()))
    return results


async def pre_render_responses(
    project_root: Path,
    provider: VoiceProvider,
    profile_ids: dict[str, str],
) -> dict[str, int]:
    counts = {}
    for character_id, texts in deterministic_responses(project_root).items():
        profile_id = profile_ids[character_id]
        for text in texts:
            await provider.synthesize(text, profile_id)
        counts[character_id] = len(texts)
    return counts


def _object_values(path: Path) -> tuple[str, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return tuple(item for item in value.values() if isinstance(item, str))


def _pool_values(path: Path) -> tuple[str, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        item
        for entries in value.values()
        if isinstance(entries, list)
        for item in entries
        if isinstance(item, str)
    )
