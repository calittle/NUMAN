import asyncio
import tempfile
import unittest
from pathlib import Path

from numan.actors import ActorRegistry, SquawkerActor
from numan.audio import QueuedAudioOutput
from numan.testing import FakeAudioBackend
from numan.voice import AudioAsset


class AudioQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_output_serializes_playback(self):
        gate = asyncio.Event()
        backend = FakeAudioBackend(hold=gate)
        output = QueuedAudioOutput("shared", backend)
        first = asyncio.create_task(output.play(AudioAsset(Path("one.wav"))))
        second = asyncio.create_task(output.play(AudioAsset(Path("two.wav"))))
        await asyncio.sleep(0)
        self.assertEqual(backend.max_active, 1)
        self.assertEqual(len(backend.plays), 1)
        gate.set()
        results = await asyncio.gather(first, second)
        self.assertTrue(all(result.played for result in results))
        self.assertEqual(backend.max_active, 1)

    async def test_drain_drops_queued_but_finishes_active(self):
        gate = asyncio.Event()
        backend = FakeAudioBackend(hold=gate)
        output = QueuedAudioOutput("shared", backend)
        first = asyncio.create_task(output.play(AudioAsset(Path("one.wav"))))
        await asyncio.sleep(0)
        second = asyncio.create_task(output.play(AudioAsset(Path("two.wav"))))
        await asyncio.sleep(0)
        output.drain()
        gate.set()
        first_result, second_result = await asyncio.gather(first, second)
        self.assertTrue(first_result.played)
        self.assertFalse(second_result.played)
        self.assertEqual([item[0].name for item in backend.plays], ["one.wav"])

    async def test_stop_releases_active_and_drops_queue(self):
        gate = asyncio.Event()
        backend = FakeAudioBackend(hold=gate)
        output = QueuedAudioOutput("shared", backend)
        first = asyncio.create_task(output.play(AudioAsset(Path("one.wav"))))
        await asyncio.sleep(0)
        second = asyncio.create_task(output.play(AudioAsset(Path("two.wav"))))
        await asyncio.sleep(0)
        self.assertTrue(await output.stop())
        first_result, second_result = await asyncio.gather(first, second)
        self.assertTrue(first_result.played)
        self.assertFalse(second_result.played)
        self.assertEqual(backend.stops, 1)

    async def test_distinct_outputs_can_play_concurrently(self):
        gate = asyncio.Event()
        left = FakeAudioBackend(hold=gate)
        right = FakeAudioBackend(hold=gate)
        left_task = asyncio.create_task(
            QueuedAudioOutput("left", left).play(AudioAsset(Path("left.wav")))
        )
        right_task = asyncio.create_task(
            QueuedAudioOutput("right", right).play(AudioAsset(Path("right.wav")))
        )
        await asyncio.sleep(0)
        self.assertEqual(left.active, 1)
        self.assertEqual(right.active, 1)
        gate.set()
        await asyncio.gather(left_task, right_task)


class ActorTests(unittest.IsolatedAsyncioTestCase):
    async def test_actor_uses_assigned_route(self):
        backend = FakeAudioBackend()
        actor = SquawkerActor(
            "bird-left", "nigel", QueuedAudioOutput("output-left", backend)
        )
        result = await actor.speak(AudioAsset(Path("speech.wav")))
        self.assertEqual(result.route_id, "output-left")
        self.assertEqual(backend.plays, [(Path("speech.wav"), "output-left")])

    async def test_actor_removes_owned_voice_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "speech.wav"
            path.write_bytes(b"wav")
            actor = SquawkerActor(
                "bird", "nigel", QueuedAudioOutput("route", FakeAudioBackend())
            )
            await actor.speak(AudioAsset(path, owned=True))
            self.assertFalse(path.exists())

    def test_registry_rejects_duplicate_actor_ids(self):
        output = QueuedAudioOutput("route", FakeAudioBackend())
        actor = SquawkerActor("bird", "nigel", output)
        with self.assertRaises(ValueError):
            ActorRegistry([actor, actor])


if __name__ == "__main__":
    unittest.main()
