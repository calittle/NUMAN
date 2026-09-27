import json
import tempfile
import unittest
from pathlib import Path

from numan.engine.models import ResponseSource, Utterance
from numan.engine.normalization import extract_drink_query, routine_text, stable_text
from numan.engine.providers import FakeLLMProvider
from numan.engine.repositories import (
    JsonExactCache,
    JsonResponsePools,
    MappingExactCache,
    MappingResponsePools,
    RepositoryFormatError,
)
from tests.support import TEST_GROG, build_grog_test_dispatcher


FIXTURES = Path(__file__).parent / "fixtures" / "dispatch_regression_cases.json"


class FakeRecipes:
    def __init__(self):
        self.calls = []

    async def lookup(self, query, character):
        self.calls.append((query, character.id))
        if query in {"a painkiller", "painkiller"}:
            return "Painkiller recipe"
        return None


def make_dispatcher():
    llm = FakeLLMProvider("LLM answer")
    recipes = FakeRecipes()
    exact = MappingExactCache({"mai tai": "Mai Tai recipe"})
    pools = MappingResponsePools(
        {
            "_greetings": ["Welcome."],
            "_parrot_taunts": ["Order a drink."],
            "_origin_stories": ["Kalapu story."],
            "_tiki_facts": ["Tiki fact."],
            "_tiki_tall_tales": ["Impossible tiki tale."],
            "_bartender_chat": ["Bar banter."],
            "recommend me something tropical": ["Try a Jungle Bird."],
        }
    )
    dispatcher = build_grog_test_dispatcher(
        exact_cache=exact,
        response_pools=pools,
        structured_data=recipes,
        llm=llm,
        chooser=lambda entries: entries[0],
    )
    return dispatcher, recipes, llm


def utterance(text):
    return Utterance(text, TEST_GROG.id, "regression-session")


class NormalizationTests(unittest.TestCase):
    def test_stable_cache_key_preserves_expected_normalization(self):
        self.assertEqual(stable_text("  What's   UP?!  "), "whats up")

    def test_routine_normalization_preserves_apostrophes(self):
        self.assertEqual(routine_text(" What's up?! "), "what's up")

    def test_drink_query_forms(self):
        cases = {
            "What's in a Mai Tai?": "mai tai",
            "How do I make a Zombie?": "zombie",
            "Recipe for Painkiller": "painkiller",
            "Describe Planter's Punch": "planter's punch",
            "Exact recipe for my Thai.": "mai tai",
            "Recipe for Mai Thai!": "mai tai",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(extract_drink_query(question), expected)

class RepositoryTests(unittest.TestCase):
    def test_json_repositories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exact_path = root / "exact.json"
            pools_path = root / "pools.json"
            exact_path.write_text(json.dumps({"mai tai": "recipe"}), encoding="utf-8")
            pools_path.write_text(
                json.dumps({"hello": ["one", "two"], "_private": ["secret"]}),
                encoding="utf-8",
            )
            self.assertEqual(JsonExactCache(exact_path).lookup("mai tai"), "recipe")
            self.assertEqual(JsonResponsePools(pools_path).match("helo")[0], "hello")

    def test_invalid_json_is_reported_with_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text("[", encoding="utf-8")
            with self.assertRaisesRegex(RepositoryFormatError, "broken.json"):
                JsonExactCache(path)


class DispatchRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_spoken_mai_tai_variant_stays_on_exact_cache_path(self):
        dispatcher, _, llm = make_dispatcher()
        plan = await dispatcher.dispatch(
            utterance("Exact recipe for my Thai."), TEST_GROG
        )
        self.assertEqual(plan.source, ResponseSource.EXACT_CACHE)
        self.assertEqual(plan.text, "Mai Tai recipe")
        self.assertEqual(llm.calls, [])

    async def test_recorded_precedence_cases(self):
        cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
        for case in cases:
            dispatcher, _, _ = make_dispatcher()
            with self.subTest(question=case["question"]):
                plan = await dispatcher.dispatch(
                    utterance(case["question"]), TEST_GROG
                )
                self.assertEqual(plan.source.value, case["expected"])

    async def test_llm_is_never_called_when_a_fast_path_hits(self):
        questions = (
            "Hello",
            "What's in a mai tai?",
            "recommend me something tropical",
            "recipe for a painkiller",
        )
        for question in questions:
            dispatcher, _, llm = make_dispatcher()
            await dispatcher.dispatch(utterance(question), TEST_GROG)
            self.assertEqual(llm.calls, [], question)

    async def test_llm_receives_character_and_conversation_scoped_utterance(self):
        dispatcher, _, llm = make_dispatcher()
        plan = await dispatcher.dispatch(
            utterance("A completely novel question"), TEST_GROG
        )
        self.assertEqual(plan.source, ResponseSource.LLM_FALLBACK)
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(llm.calls[0][0].conversation_id, "regression-session")
        self.assertIs(llm.calls[0][1], TEST_GROG)

    async def test_trace_explains_winner_and_has_timings(self):
        dispatcher, _, _ = make_dispatcher()
        trace = await dispatcher.dispatch_with_trace(
            utterance("What's in a mai tai?"), TEST_GROG
        )
        self.assertEqual(trace.attempted_rules, ("routines", "exact_cache"))
        self.assertFalse(trace.attempts[0].matched)
        self.assertTrue(trace.attempts[1].matched)
        self.assertGreaterEqual(trace.total_duration_ms, 0)
        self.assertTrue(all(item.duration_ms >= 0 for item in trace.attempts))


if __name__ == "__main__":
    unittest.main()
