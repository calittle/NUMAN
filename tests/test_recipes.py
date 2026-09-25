import unittest

from numan.application import PROJECT_ROOT
from numan.characters import NIGEL
from numan.characters.nigel_dispatch import build_nigel_dispatcher
from numan.engine.models import ResponseSource, Utterance
from numan.engine.providers import FakeLLMProvider
from numan.engine.repositories import MappingExactCache, MappingResponsePools
from numan.recipes import JsonCocktailProvider


class RecipeProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_alias_lookup_formats_spoken_units(self):
        provider = JsonCocktailProvider(PROJECT_ROOT / "data/cocktails/recipes.json")
        result = await provider.lookup("pain killer", NIGEL)
        self.assertIn("2 ounces of Pusser's rum", result)
        self.assertIn("1 ounce of cream of coconut", result)
        self.assertIn("freshly grated nutmeg", result)

    async def test_unknown_recipe_is_a_clean_miss(self):
        provider = JsonCocktailProvider(PROJECT_ROOT / "data/cocktails/recipes.json")
        self.assertIsNone(await provider.lookup("banana surprise", NIGEL))

    async def test_structured_recipe_prevents_llm_invention(self):
        llm = FakeLLMProvider("invented nonsense")
        dispatcher = build_nigel_dispatcher(
            exact_cache=MappingExactCache({}),
            response_pools=MappingResponsePools({}),
            structured_data=JsonCocktailProvider(
                PROJECT_ROOT / "data/cocktails/recipes.json"
            ),
            llm=llm,
        )
        plan = await dispatcher.dispatch(
            Utterance("Exact recipe for a Jungle Bird.", "nigel", "recipes"), NIGEL
        )
        self.assertEqual(plan.source, ResponseSource.STRUCTURED_LOOKUP)
        self.assertIn("45 millilitres of blackstrap rum", plan.text)
        self.assertEqual(llm.calls, [])


if __name__ == "__main__":
    unittest.main()
