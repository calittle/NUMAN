"""Local structured cocktail knowledge with deterministic spoken formatting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .engine.models import Character
from .engine.normalization import stable_text


class RecipeFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Ingredient:
    amount: str
    unit: str
    name: str


@dataclass(frozen=True, slots=True)
class CocktailRecipe:
    name: str
    aliases: tuple[str, ...]
    ingredients: tuple[Ingredient, ...]
    garnish: str | None
    source: str


class JsonCocktailProvider:
    def __init__(self, path: str | Path) -> None:
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
            recipes = tuple(self._parse(item) for item in raw)
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RecipeFormatError(f"cannot load cocktail recipes from {source}: {exc}") from exc
        self._recipes: dict[str, CocktailRecipe] = {}
        for recipe in recipes:
            for label in (recipe.name, *recipe.aliases):
                key = _recipe_key(label)
                if key in self._recipes:
                    raise RecipeFormatError(f"duplicate cocktail alias: {label}")
                self._recipes[key] = recipe

    @staticmethod
    def _parse(raw) -> CocktailRecipe:
        ingredients = tuple(
            Ingredient(str(item["amount"]), str(item["unit"]), str(item["name"]))
            for item in raw["ingredients"]
        )
        if not ingredients:
            raise RecipeFormatError("cocktail recipe has no ingredients")
        return CocktailRecipe(
            name=str(raw["name"]),
            aliases=tuple(str(value) for value in raw.get("aliases", ())),
            ingredients=ingredients,
            garnish=str(raw["garnish"]) if raw.get("garnish") else None,
            source=str(raw["source"]),
        )

    async def lookup(self, query: str, character: Character) -> str | None:
        del character
        recipe = self._recipes.get(_recipe_key(query))
        return format_recipe(recipe) if recipe else None


def _recipe_key(value: str) -> str:
    key = stable_text(value)
    for article in ("a ", "an ", "the "):
        if key.startswith(article):
            return key[len(article):]
    return key


def format_recipe(recipe: CocktailRecipe) -> str:
    parts = [
        f"{item.amount} {_spoken_unit(item.amount, item.unit)} of {item.name}"
        for item in recipe.ingredients
    ]
    ingredients = _join(parts)
    garnish = f", garnished with {recipe.garnish}" if recipe.garnish else ""
    return f"A {recipe.name} uses {ingredients}{garnish}."


def _spoken_unit(amount: str, unit: str) -> str:
    singular = amount.strip() in {"1", "1.0"}
    forms = {
        "ml": ("millilitre", "millilitres"),
        "oz": ("ounce", "ounces"),
        "tsp": ("teaspoon", "teaspoons"),
        "dash": ("dash", "dashes"),
        "drop": ("drop", "drops"),
    }
    one, many = forms.get(unit, (unit, unit))
    return one if singular else many


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"
