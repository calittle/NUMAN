import unittest

from numan.engine.dispatch import Dispatcher
from numan.engine.models import ResponsePlan, ResponseSource, Utterance
from numan.engine.rules import (
    ExactCacheRule,
    LLMFallbackRule,
    ResponsePoolRule,
    RoutineRule,
    StructuredLookupRule,
)
from tests.support import TEST_NIGEL


def utterance(text="hello"):
    return Utterance(text=text, character_id="nigel", conversation_id="table-1")


def routine_plan(item, character):
    return ResponsePlan(
        character_id=character.id,
        conversation_id=item.conversation_id,
        source=ResponseSource.ROUTINE,
        text="routine",
    )


class DispatcherPrecedenceTests(unittest.IsolatedAsyncioTestCase):
    def make_dispatcher(self, calls, *, routine_matches=False, exact=None, pool=None, db=None):
        async def lookup(item, character):
            calls.append("db")
            return db

        async def fallback(item, character):
            calls.append("llm")
            return "llm"

        def match_pool(text):
            calls.append("pool")
            return "greetings" if pool else None

        def match_routine(text):
            calls.append("routine")
            return routine_matches

        return Dispatcher([
            RoutineRule([("greeting", match_routine, routine_plan)]),
            ExactCacheRule(exact or {}),
            ResponsePoolRule(
                {"greetings": [pool]} if pool else {},
                matcher=match_pool,
                chooser=lambda entries: entries[0],
            ),
            StructuredLookupRule(lookup),
            LLMFallbackRule(fallback),
        ])

    async def test_routine_wins_and_stops_chain(self):
        calls = []
        result = await self.make_dispatcher(
            calls, routine_matches=True, exact={"hello": "cache"}, pool="pool", db="db"
        ).dispatch(utterance(), TEST_NIGEL)
        self.assertEqual(result.source, ResponseSource.ROUTINE)
        self.assertEqual(calls, ["routine"])

    async def test_exact_cache_precedes_pool_database_and_llm(self):
        calls = []
        result = await self.make_dispatcher(
            calls, exact={"hello": "cache"}, pool="pool", db="db"
        ).dispatch(utterance("  HELLO  "), TEST_NIGEL)
        self.assertEqual(result.text, "cache")
        self.assertEqual(result.source, ResponseSource.EXACT_CACHE)
        self.assertEqual(calls, ["routine"])

    async def test_pool_precedes_structured_lookup(self):
        calls = []
        result = await self.make_dispatcher(calls, pool="pool", db="db").dispatch(
            utterance(), TEST_NIGEL
        )
        self.assertEqual(result.source, ResponseSource.RESPONSE_POOL)
        self.assertEqual(calls, ["routine", "pool"])

    async def test_structured_lookup_precedes_llm(self):
        calls = []
        result = await self.make_dispatcher(calls, db="db").dispatch(
            utterance(), TEST_NIGEL
        )
        self.assertEqual(result.source, ResponseSource.STRUCTURED_LOOKUP)
        self.assertEqual(calls, ["routine", "pool", "db"])

    async def test_llm_is_last_resort(self):
        calls = []
        result = await self.make_dispatcher(calls).dispatch(utterance(), TEST_NIGEL)
        self.assertEqual(result.source, ResponseSource.LLM_FALLBACK)
        self.assertEqual(calls, ["routine", "pool", "db", "llm"])

    async def test_trace_names_only_rules_that_ran(self):
        trace = await self.make_dispatcher([], db="db").dispatch_with_trace(
            utterance(), TEST_NIGEL
        )
        self.assertEqual(
            trace.attempted_rules,
            ("routines", "exact_cache", "response_pool", "structured_lookup"),
        )

    async def test_character_mismatch_is_rejected(self):
        dispatcher = self.make_dispatcher([])
        with self.assertRaises(ValueError):
            await dispatcher.dispatch(
                Utterance("hello", "someone-else", "table-1"), TEST_NIGEL
            )


class ContractTests(unittest.TestCase):
    def test_utterance_requires_conversation_scope(self):
        with self.assertRaises(ValueError):
            Utterance("hello", "nigel", "")

    def test_empty_response_plan_is_invalid(self):
        with self.assertRaises(ValueError):
            ResponsePlan("nigel", "table-1", ResponseSource.ROUTINE)

    def test_metadata_is_copied_and_read_only(self):
        original = {"source": "mic"}
        item = Utterance("hello", "nigel", "table-1", original)
        original["source"] = "changed"
        self.assertEqual(item.metadata["source"], "mic")
        with self.assertRaises(TypeError):
            item.metadata["source"] = "changed"


if __name__ == "__main__":
    unittest.main()
