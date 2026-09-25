import unittest

from numan.application import PROJECT_ROOT, build_application
from numan.configuration import load_config
from numan.engine.models import ResponseSource, Utterance
from numan.engine.repositories import JsonResponsePools


class CharacterContentTests(unittest.IsolatedAsyncioTestCase):
    def test_each_character_has_varied_private_pools(self):
        required = {
            "_greetings",
            "_parrot_taunts",
            "_origin_stories",
            "_tiki_facts",
            "_tiki_tall_tales",
            "_bartender_chat",
        }
        repositories = {
            character: JsonResponsePools(
                PROJECT_ROOT / f"data/{character}/response_pools.json"
            )
            for character in ("nigel", "polly")
        }
        for repository in repositories.values():
            for pool in required:
                self.assertGreaterEqual(len(repository.entries(pool)), 6)
        self.assertTrue(
            set(repositories["nigel"].entries("_parrot_taunts")).isdisjoint(
                repositories["polly"].entries("_parrot_taunts")
            )
        )

    async def test_same_taunt_prompt_routes_to_each_characters_own_pool(self):
        application = build_application(
            load_config(PROJECT_ROOT / "config/numan.toml"), live=False
        )
        results = {}
        for character_id in ("nigel", "polly"):
            character = application.characters[character_id]
            results[character_id] = await application.orchestrator.perform(
                Utterance("Are you a parrot?", character_id, "taunt-test"),
                character,
                f"{character_id}-dev",
            )

        self.assertEqual(results["nigel"].plan.source, ResponseSource.ROUTINE)
        self.assertEqual(results["polly"].plan.source, ResponseSource.ROUTINE)
        self.assertEqual(results["nigel"].plan.metadata["routine"], "parrot_taunt")
        self.assertEqual(results["polly"].plan.metadata["routine"], "parrot_taunt")
        self.assertNotEqual(results["nigel"].plan.text, results["polly"].plan.text)


if __name__ == "__main__":
    unittest.main()
