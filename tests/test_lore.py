import json
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path

from numan.application import PROJECT_ROOT, build_application
from numan.configuration import load_config
from numan.conversations import ConversationKey, InMemoryConversationStore, TurnRole
from numan.engine.providers import FakeLLMProvider
from numan.engine.rules import VenueLoreRule, ProviderLLMFallbackRule
from tests.support import TEST_GROG
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

    async def test_reworded_and_unknown_lore_never_calls_model(self):
        application = build_application(
            load_config(PROJECT_ROOT / "config/numan.toml"), live=False)
        application.llm_provider.complete = Mock(side_effect=AssertionError("Lore reached LLM"))
        application.llm_provider.stream = Mock(side_effect=AssertionError("Lore reached streaming LLM"))
        for character_id in ("grog", "polly"):
            for phrase in (
                "Explain Kraken's Curse history in a poem",
                "What colour are the Kraken's eyes?",
                "Could you explain Elira's sacrifice?",
                "Tell me about Sister Mairead Solène",
                "Was Isara friends with Datura?",
                "Invent a new pact for the Pactbound Nine",
                "What secrets does this bar keep?",
                "What is in the grimoire?",
                "Who founded the cracking curse?",
            ):
                with self.subTest(character=character_id, phrase=phrase):
                    result = await application.orchestrator.perform(
                        Utterance(phrase, character_id, "guard"),
                        application.characters[character_id], character_id + "-dev")
                    self.assertEqual(result.plan.source, ResponseSource.VENUE_LORE)
                    self.assertEqual(result.dispatch_trace.attempts[-1].rule, "venue_lore")
                    application.llm_provider.complete.assert_not_called()
                    application.llm_provider.stream.assert_not_called()

    async def test_followup_and_history_are_kept_out_of_model(self):
        provider = JsonLoreProvider(PROJECT_ROOT / "data/krakens_curse/lore.json")
        store = InMemoryConversationStore()
        key = ConversationKey("grog", "protected")
        question = "Who was Elira?"
        answer, _ = await provider.lookup(question, TEST_GROG)
        await store.append(key, TurnRole.USER, question)
        await store.append(key, TurnRole.ASSISTANT, answer)
        followup = Utterance("Why did she do that?", "grog", "protected")
        await store.append(key, TurnRole.USER, followup.text)
        plan = await VenueLoreRule(provider, store).evaluate(followup, TEST_GROG)
        self.assertEqual(plan.source, ResponseSource.VENUE_LORE)
        await store.append(key, TurnRole.ASSISTANT, plan.text)
        unrelated = Utterance("What do parrots dream about?", "grog", "protected")
        await store.append(key, TurnRole.USER, unrelated.text)
        llm = FakeLLMProvider("Generic reply")
        self.assertIsNone(await VenueLoreRule(provider, store).evaluate(unrelated, TEST_GROG))
        await ProviderLLMFallbackRule(llm, store, venue_lore=provider).evaluate(unrelated, TEST_GROG)
        self.assertEqual([turn.text for turn in llm.histories[0]], [unrelated.text])

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
