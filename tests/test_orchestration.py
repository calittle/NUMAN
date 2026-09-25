import unittest
import tempfile
from pathlib import Path

from numan.actors import ActorRegistry, SquawkerActor
from numan.audio import QueuedAudioOutput
from numan.characters import NIGEL
from numan.characters.nigel_dispatch import build_nigel_dispatcher
from numan.engine.models import Utterance
from numan.engine.providers import FakeLLMProvider, NullStructuredDataProvider
from numan.engine.repositories import MappingExactCache, MappingResponsePools
from numan.orchestration import Orchestrator
from numan.performance import StallingCue, StallingPlan
from numan.testing import FakeAudioBackend, FakeVoiceProvider


def make_orchestrator(actor_character="nigel"):
    dispatcher = build_nigel_dispatcher(
        exact_cache=MappingExactCache({"mai tai": "Mai Tai recipe"}),
        response_pools=MappingResponsePools({"_greetings": ["Hello there."]}),
        structured_data=NullStructuredDataProvider(),
        llm=FakeLLMProvider("LLM answer"),
        chooser=lambda values: values[0],
    )
    voice = FakeVoiceProvider()
    backend = FakeAudioBackend()
    actor = SquawkerActor(
        "bird-one", actor_character, QueuedAudioOutput("speaker-one", backend)
    )
    return Orchestrator(dispatcher, voice, ActorRegistry([actor])), voice, backend


class OrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_synthesis_and_actor_route(self):
        orchestrator, voice, backend = make_orchestrator()
        result = await orchestrator.perform(
            Utterance("Hello", "nigel", "conversation-7"), NIGEL, "bird-one"
        )
        self.assertEqual(voice.calls, [("Hello there.", NIGEL.voice_profile)])
        self.assertEqual(backend.plays[0][1], "speaker-one")
        self.assertEqual(result.actor_id, "bird-one")
        self.assertEqual(result.route_id, "speaker-one")
        self.assertTrue(result.played)
        self.assertGreaterEqual(result.timings.total_ms, 0)
        self.assertFalse(result.stall_played)

    async def test_cached_stall_opener_plays_only_for_llm_fallback(self):
        dispatcher = build_nigel_dispatcher(
            exact_cache=MappingExactCache({}),
            response_pools=MappingResponsePools({"_greetings": ["Hello there."]}),
            structured_data=NullStructuredDataProvider(),
            llm=FakeLLMProvider("LLM answer"),
            chooser=lambda values: values[0],
        )
        voice = FakeVoiceProvider()
        backend = FakeAudioBackend()
        actor = SquawkerActor(
            "bird-one", "nigel", QueuedAudioOutput("speaker-one", backend)
        )
        with tempfile.TemporaryDirectory() as directory:
            opener = Path(directory) / "opener.wav"
            opener.touch()
            plan = StallingPlan((StallingCue("Thinking", opener),), (), "Ready")
            orchestrator = Orchestrator(
                dispatcher, voice, ActorRegistry([actor]), stalling=plan
            )
            result = await orchestrator.perform(
                Utterance("An uncached question", "nigel", "conversation-7"),
                NIGEL,
                "bird-one",
            )

        self.assertTrue(result.stall_played)
        self.assertEqual(
            [path for path, _ in backend.plays],
            [opener, Path("memory-1.wav")],
        )

    async def test_stall_opener_is_not_used_for_fast_response(self):
        orchestrator, _, backend = make_orchestrator()
        result = await orchestrator.perform(
            Utterance("Hello", "nigel", "conversation-7"), NIGEL, "bird-one"
        )
        self.assertFalse(result.stall_played)
        self.assertEqual(len(backend.plays), 1)

    async def test_stall_opener_does_not_repeat_when_alternatives_exist(self):
        dispatcher = build_nigel_dispatcher(
            exact_cache=MappingExactCache({}),
            response_pools=MappingResponsePools({}),
            structured_data=NullStructuredDataProvider(),
            llm=FakeLLMProvider("LLM answer"),
        )
        backend = FakeAudioBackend()
        registered = SquawkerActor(
            "bird-one", "nigel", QueuedAudioOutput("speaker-one", backend)
        )
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.wav"
            second = Path(directory) / "second.wav"
            first.touch()
            second.touch()
            plan = StallingPlan(
                (StallingCue("First", first), StallingCue("Second", second)),
                (),
                "Ready",
            )
            orchestrator = Orchestrator(
                dispatcher, FakeVoiceProvider(), ActorRegistry([registered]), stalling=plan
            )
            await orchestrator.perform(
                Utterance("Question one", "nigel", "one"), NIGEL, "bird-one"
            )
            await orchestrator.perform(
                Utterance("Question two", "nigel", "two"), NIGEL, "bird-one"
            )

        self.assertNotEqual(backend.plays[0][0], backend.plays[2][0])

    async def test_wrong_character_actor_is_rejected_before_synthesis(self):
        orchestrator, voice, _ = make_orchestrator("another-character")
        with self.assertRaises(ValueError):
            await orchestrator.perform(
                Utterance("Hello", "nigel", "conversation-7"), NIGEL, "bird-one"
            )
        self.assertEqual(voice.calls, [])

    async def test_unknown_actor_is_clear_error(self):
        orchestrator, _, _ = make_orchestrator()
        with self.assertRaisesRegex(LookupError, "missing"):
            await orchestrator.perform(
                Utterance("Hello", "nigel", "conversation-7"), NIGEL, "missing"
            )


if __name__ == "__main__":
    unittest.main()
