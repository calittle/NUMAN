import asyncio
import unittest
import tempfile
from pathlib import Path

from numan.actors import ActorRegistry, SquawkerActor
from numan.audio import QueuedAudioOutput
from numan.engine.models import Utterance
from numan.engine.providers import FakeLLMProvider, NullStructuredDataProvider
from numan.engine.repositories import MappingExactCache, MappingResponsePools
from numan.orchestration import Orchestrator
from numan.performance import StallingCue, StallingPlan
from numan.testing import FakeAudioBackend, FakeVoiceProvider
from tests.support import TEST_GROG, build_grog_test_dispatcher


def make_orchestrator(actor_character="grog"):
    dispatcher = build_grog_test_dispatcher(
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
            Utterance("Hello", "grog", "conversation-7"), TEST_GROG, "bird-one"
        )
        self.assertEqual(voice.calls, [("Hello there.", TEST_GROG.voice_profile)])
        self.assertEqual(backend.plays[0][1], "speaker-one")
        self.assertEqual(result.actor_id, "bird-one")
        self.assertEqual(result.route_id, "speaker-one")
        self.assertTrue(result.played)
        self.assertGreaterEqual(result.timings.total_ms, 0)
        self.assertFalse(result.stall_played)

    async def test_streaming_llm_synthesizes_and_plays_complete_sentences(self):
        class StreamingLLM:
            async def complete(self, *args):
                raise AssertionError("streaming path should be selected")

            async def stream(self, *args):
                for fragment in ("First sentence.", " Second", " sentence."):
                    await asyncio.sleep(0)
                    yield fragment

        dispatcher = build_grog_test_dispatcher(
            exact_cache=MappingExactCache({}),
            response_pools=MappingResponsePools({}),
            structured_data=NullStructuredDataProvider(),
            llm=StreamingLLM(),
        )
        voice = FakeVoiceProvider()
        backend = FakeAudioBackend()
        actor = SquawkerActor(
            "bird-one", "grog", QueuedAudioOutput("speaker-one", backend)
        )
        orchestrator = Orchestrator(dispatcher, voice, ActorRegistry([actor]))

        result = await orchestrator.perform(
            Utterance("Uncached", "grog", "stream"), TEST_GROG, "bird-one"
        )

        self.assertEqual(result.plan.text, "First sentence. Second sentence.")
        self.assertEqual(
            voice.calls,
            [
                ("First sentence.", TEST_GROG.voice_profile),
                ("Second sentence.", TEST_GROG.voice_profile),
            ],
        )
        self.assertEqual(len(backend.plays), 2)
        self.assertGreaterEqual(result.timings.llm_total_ms, 0)

    async def test_cached_stall_opener_plays_only_for_llm_fallback(self):
        dispatcher = build_grog_test_dispatcher(
            exact_cache=MappingExactCache({}),
            response_pools=MappingResponsePools({"_greetings": ["Hello there."]}),
            structured_data=NullStructuredDataProvider(),
            llm=FakeLLMProvider("LLM answer"),
            chooser=lambda values: values[0],
        )
        voice = FakeVoiceProvider()
        backend = FakeAudioBackend()
        actor = SquawkerActor(
            "bird-one", "grog", QueuedAudioOutput("speaker-one", backend)
        )
        with tempfile.TemporaryDirectory() as directory:
            opener = Path(directory) / "opener.wav"
            opener.touch()
            plan = StallingPlan((StallingCue("Thinking", opener),), (), "Ready")
            orchestrator = Orchestrator(
                dispatcher, voice, ActorRegistry([actor]), stalling=plan
            )
            result = await orchestrator.perform(
                Utterance("An uncached question", "grog", "conversation-7"),
                TEST_GROG,
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
            Utterance("Hello", "grog", "conversation-7"), TEST_GROG, "bird-one"
        )
        self.assertFalse(result.stall_played)
        self.assertEqual(len(backend.plays), 1)

    async def test_stall_opener_does_not_repeat_when_alternatives_exist(self):
        dispatcher = build_grog_test_dispatcher(
            exact_cache=MappingExactCache({}),
            response_pools=MappingResponsePools({}),
            structured_data=NullStructuredDataProvider(),
            llm=FakeLLMProvider("LLM answer"),
        )
        backend = FakeAudioBackend()
        registered = SquawkerActor(
            "bird-one", "grog", QueuedAudioOutput("speaker-one", backend)
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
                Utterance("Question one", "grog", "one"), TEST_GROG, "bird-one"
            )
            await orchestrator.perform(
                Utterance("Question two", "grog", "two"), TEST_GROG, "bird-one"
            )

        self.assertNotEqual(backend.plays[0][0], backend.plays[2][0])

    async def test_audio_opener_covers_transcription_without_second_llm_opener(self):
        started = asyncio.Event()
        release = asyncio.Event()
        transcribed = asyncio.Event()
        opener = Path(__file__).parents[1] / "data/grog/audio/let-me-think.wav"

        class BlockingBackend(FakeAudioBackend):
            async def play(self, path, route_id):
                await super().play(path, route_id)
                if path == opener:
                    started.set()
                    await release.wait()

        orchestrator, _, _ = make_orchestrator()
        backend = BlockingBackend()
        orchestrator._actors = ActorRegistry([SquawkerActor(
            "bird-one", "grog", QueuedAudioOutput("speaker-one", backend)
        )])
        orchestrator._stalling = StallingPlan(
            (StallingCue("Thinking", opener),), (), "Ready"
        )

        async def transcribe(audio):
            await asyncio.wait_for(started.wait(), 1)
            transcribed.set()
            return "An uncached question"

        task = asyncio.create_task(orchestrator.perform_audio(
            Path("question.wav"), transcribe, TEST_GROG, "bird-one", "voice"
        ))
        try:
            await asyncio.wait_for(transcribed.wait(), 1)
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            self.assertEqual([p for p, _ in backend.plays], [opener])
        finally:
            release.set()
        result = await asyncio.wait_for(task, 1)
        self.assertTrue(result.stall_played)
        self.assertEqual([p for p, _ in backend.plays], [opener, Path("memory-1.wav")])

    async def test_transcription_failure_cancels_active_opener(self):
        started = asyncio.Event()
        stopped = asyncio.Event()

        class BlockingBackend(FakeAudioBackend):
            async def play(self, path, route_id):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

        orchestrator, voice, _ = make_orchestrator()
        orchestrator._actors = ActorRegistry([SquawkerActor(
            "bird-one", "grog", QueuedAudioOutput("speaker-one", BlockingBackend())
        )])
        from numan.performance import GROG_STALLING_PLAN
        orchestrator._stalling = GROG_STALLING_PLAN

        async def transcribe(audio):
            await asyncio.wait_for(started.wait(), 1)
            raise RuntimeError("transcription failed")

        with self.assertRaisesRegex(RuntimeError, "transcription failed"):
            await orchestrator.perform_audio(
                Path("question.wav"), transcribe, TEST_GROG, "bird-one", "voice"
            )
        self.assertTrue(stopped.is_set())
        self.assertEqual(voice.calls, [])

    async def test_polly_has_playable_cached_openers_in_application(self):
        import wave
        from numan.application import PROJECT_ROOT, build_application
        from numan.configuration import load_config
        from numan.performance import POLLY_STALLING_PLAN
        app = build_application(load_config(PROJECT_ROOT / "config/numan.toml"), live=False)
        for cue in POLLY_STALLING_PLAN.openers:
            with wave.open(str(cue.audio_asset)) as wav:
                self.assertGreater(wav.getnframes(), 0)
                self.assertEqual(wav.getsampwidth(), 2)

        async def transcribe(audio):
            return "Hello"

        result = await app.orchestrator.perform_audio(
            Path("question.wav"), transcribe, app.characters["polly"], "polly-dev", "voice"
        )
        self.assertTrue(result.stall_played)
        self.assertEqual(result.actor_id, "polly-dev")
        self.assertGreaterEqual(
            result.timings.answer_start_ms, result.timings.transcription_ms
        )

    async def test_wrong_character_actor_is_rejected_before_synthesis(self):
        orchestrator, voice, _ = make_orchestrator("another-character")
        with self.assertRaises(ValueError):
            await orchestrator.perform(
                Utterance("Hello", "grog", "conversation-7"), TEST_GROG, "bird-one"
            )
        self.assertEqual(voice.calls, [])

    async def test_unknown_actor_is_clear_error(self):
        orchestrator, _, _ = make_orchestrator()
        with self.assertRaisesRegex(LookupError, "missing"):
            await orchestrator.perform(
                Utterance("Hello", "grog", "conversation-7"), TEST_GROG, "missing"
            )


if __name__ == "__main__":
    unittest.main()
