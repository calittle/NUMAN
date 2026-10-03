import json
import tempfile
import unittest
from pathlib import Path

from numan.application import PROJECT_ROOT
from numan.engine.models import ResponseSource, Utterance
from numan.engine.providers import FakeLLMProvider
from numan.engine.repositories import MappingExactCache, MappingResponsePools
from numan.recipes import JsonCocktailProvider, LayeredCocktailProvider
from tests.support import TEST_GROG, build_grog_test_dispatcher


class RecipeProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_alias_lookup_formats_spoken_units(self):
        provider = JsonCocktailProvider(PROJECT_ROOT / "data/cocktails/recipes.json")
        result = await provider.lookup("pain killer", TEST_GROG)
        self.assertIn("2 ounces of Pusser's rum", result)
        self.assertIn("1 ounce of cream of coconut", result)
        self.assertIn("freshly grated nutmeg", result)

    async def test_unknown_recipe_is_a_clean_miss(self):
        provider = JsonCocktailProvider(PROJECT_ROOT / "data/cocktails/recipes.json")
        self.assertIsNone(await provider.lookup("banana surprise", TEST_GROG))

    async def test_grimoire_catalog_contains_nine_preparation_complete_drinks(self):
        provider = JsonCocktailProvider(
            PROJECT_ROOT / "data/krakens_curse/recipes.json"
        )
        self.assertEqual(len(provider.recipes), 9)
        self.assertTrue(all(recipe.preparation for recipe in provider.recipes))
        result = await provider.lookup("Chalice of the Forsaken", TEST_GROG)
        self.assertIn("Wray & Nephew", result)
        self.assertIn("To prepare it, shake", result)

    async def test_house_recipe_overrides_reference_recipe(self):
        house = [{
            "name": "Mai Tai", "aliases": [], "source": "Kraken's Curse",
            "ingredients": [{"amount": "2", "unit": "oz", "name": "house rum"}],
            "garnish": "mint",
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "house.json"
            path.write_text(json.dumps(house), encoding="utf-8")
            provider = LayeredCocktailProvider(
                JsonCocktailProvider(path),
                JsonCocktailProvider(PROJECT_ROOT / "data/cocktails/recipes.json"),
            )
            result = await provider.lookup("Mai Tai", TEST_GROG)
        self.assertIn("2 ounces of house rum", result)

    async def test_structured_recipe_prevents_llm_invention(self):
        llm = FakeLLMProvider("invented nonsense")
        dispatcher = build_grog_test_dispatcher(
            exact_cache=MappingExactCache({}),
            response_pools=MappingResponsePools({}),
            structured_data=JsonCocktailProvider(
                PROJECT_ROOT / "data/cocktails/recipes.json"
            ),
            llm=llm,
        )
        plan = await dispatcher.dispatch(
            Utterance("Exact recipe for a Jungle Bird.", "grog", "recipes"), TEST_GROG
        )
        self.assertEqual(plan.source, ResponseSource.STRUCTURED_LOOKUP)
        self.assertIn("45 millilitres of blackstrap rum", plan.text)
        self.assertEqual(llm.calls, [])

    async def test_make_me_phrase_uses_structured_recipe(self):
        llm = FakeLLMProvider("invented nonsense")
        dispatcher = build_grog_test_dispatcher(
            exact_cache=MappingExactCache({}),
            response_pools=MappingResponsePools({}),
            structured_data=JsonCocktailProvider(
                PROJECT_ROOT / "data/cocktails/recipes.json"
            ),
            llm=llm,
        )
        plan = await dispatcher.dispatch(
            Utterance("Make me a Mai Tai.", "grog", "recipes"), TEST_GROG
        )
        self.assertEqual(plan.source, ResponseSource.STRUCTURED_LOOKUP)
        self.assertTrue(plan.text.startswith("A Mai Tai uses"))
        self.assertEqual(llm.calls, [])


if __name__ == "__main__":
    unittest.main()
