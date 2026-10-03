import json
import tempfile
import unittest
from pathlib import Path

from numan.application import PROJECT_ROOT, build_application
from numan.configuration import load_config
from numan.engine.models import ResponseSource, Utterance
from numan.lore import JsonLoreProvider, LoreFormatError


class LoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_house_lore_routes_before_ollama_with_character_voice(self):
        application = build_application(
            load_config(PROJECT_ROOT / "config/numan.toml"), live=False
        )
        character = application.characters["polly"]
        result = await application.orchestrator.perform(
            Utterance("Tell me about the Kraken's Curse", "polly", "lore"),
            character,
            "polly-dev",
        )
        self.assertEqual(result.plan.source, ResponseSource.VENUE_LORE)
        self.assertIn("unmapped island", result.plan.text)
        self.assertEqual(result.plan.metadata["lore_id"], "legend_of_the_bar")

    async def test_natural_find_the_bar_phrases_route_to_lore(self):
        application = build_application(
            load_config(PROJECT_ROOT / "config/numan.toml"), live=False
        )
        character = application.characters["grog"]
        for phrase in (
            "How to find the Kraken's Curse?",
            "How do I find the Kraken's Curse?",
            "Where is the Kraken's Curse?",
            "Where can I find the Kraken's Curse?",
            "How to find the crackin' curse?",
        ):
            with self.subTest(phrase=phrase):
                result = await application.orchestrator.perform(
                    Utterance(phrase, "grog", "find-the-bar"),
                    character,
                    "grog-dev",
                )
                self.assertEqual(result.plan.source, ResponseSource.VENUE_LORE)
                self.assertEqual(result.plan.metadata["lore_id"], "finding_the_bar")

    def test_duplicate_aliases_are_rejected(self):
        entries = [
            {"id": "a", "aliases": ["where"], "source": "owner",
             "responses": {"default": "Here."}},
            {"id": "b", "aliases": ["WHERE!"], "source": "owner",
             "responses": {"default": "There."}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lore.json"
            path.write_text(json.dumps(entries), encoding="utf-8")
            with self.assertRaisesRegex(LoreFormatError, "duplicate lore alias"):
                JsonLoreProvider(path)


if __name__ == "__main__":
    unittest.main()
