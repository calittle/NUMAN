import asyncio
import unittest

from numan.actors import ActorRegistry, SquawkerActor
from numan.application import PROJECT_ROOT, build_application
from numan.audio import QueuedAudioOutput
from numan.configuration import load_config
from numan.engine.dispatch import Dispatcher
from numan.engine.models import Character, ResponsePlan, ResponseSource, Utterance
from numan.show_control import (
    DrinkPresentationCatalog,
    FakeLightORamaProvider,
    ShowAction,
    ShowActionScheduler,
)
from numan.orchestration import Orchestrator
from numan.testing import FakeAudioBackend, FakeVoiceProvider


class DrinkPresentationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.catalog = DrinkPresentationCatalog(
            PROJECT_ROOT / "data/show/drink_presentations.json"
        )

    def test_intent_is_required_and_recipe_question_does_not_match(self):
        self.assertIsNone(self.catalog.match("What's in a Jet Pilot?", "polly"))
        self.assertIsNone(
            self.catalog.match("I want the recipe for a Jet Pilot", "polly")
        )
        presentation, intent = self.catalog.match("I want a Jet Pilot", "polly")
        self.assertEqual((presentation.drink_id, intent), ("jet_pilot", "ordering"))
        presentation, intent = self.catalog.match(
            "I'm serving a Suffering Bastard", "nigel"
        )
        self.assertEqual(
            (presentation.drink_id, intent), ("suffering_bastard", "serving")
        )

    async def test_order_schedules_two_minutes_and_can_be_cancelled(self):
        application = build_application(
            load_config(PROJECT_ROOT / "config/numan.toml"), live=False
        )
        result = await application.orchestrator.perform(
            Utterance("I want a Jet Pilot", "polly", "bar-seat-3"),
            application.characters["polly"],
            "polly-dev",
        )

        cue = result.scheduled_actions[0]
        self.assertEqual(cue.action.name, "present_jet_pilot")
        self.assertEqual(cue.delay_seconds, 120)
        self.assertEqual(cue.status, "scheduled")
        self.assertEqual(application.show_control.triggered, [])
        self.assertTrue(application.show_scheduler.cancel(cue.id))
        await application.show_scheduler.shutdown()

    async def test_serving_cue_fires_immediately_after_response(self):
        application = build_application(
            load_config(PROJECT_ROOT / "config/numan.toml"), live=False
        )
        result = await application.orchestrator.perform(
            Utterance("I'm serving a Suffering Bastard", "nigel", "service"),
            application.characters["nigel"],
            "nigel-dev",
        )

        cue = result.scheduled_actions[0]
        self.assertEqual(cue.status, "fired")
        self.assertEqual(cue.delay_seconds, 0)
        self.assertEqual(application.show_control.triggered[0].name, "present_suffering_bastard")
        self.assertEqual(
            application.show_control.triggered[0].parameters["intent"], "serving"
        )


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_delay_is_non_blocking_and_duplicate_is_suppressed(self):
        provider = FakeLightORamaProvider({"effect"})
        scheduler = ShowActionScheduler(provider)
        first = await scheduler.schedule(
            ShowAction("effect"), character_id="bird", conversation_id="one",
            delay_seconds=0.02, cooldown_seconds=1,
        )
        duplicate = await scheduler.schedule(
            ShowAction("effect"), character_id="bird", conversation_id="two",
            delay_seconds=0.02, cooldown_seconds=1,
        )
        self.assertEqual(first.status, "scheduled")
        self.assertEqual(duplicate.status, "suppressed")
        self.assertEqual(provider.triggered, [])
        await asyncio.sleep(0.04)
        self.assertEqual(first.status, "fired")
        self.assertEqual([action.name for action in provider.triggered], ["effect"])
        await scheduler.shutdown()

    async def test_immediate_action_waits_for_spoken_response_to_finish(self):
        class StaticRule:
            name = "static"

            async def evaluate(self, utterance, character):
                return ResponsePlan(
                    character.id, utterance.conversation_id, ResponseSource.ROUTINE,
                    text="Brace yourself.", show_actions=("storm",),
                )

        release = asyncio.Event()
        backend = FakeAudioBackend(hold=release)
        provider = FakeLightORamaProvider({"storm"})
        character = Character(
            "bird", "Bird", "", "voice", frozenset({"storm"})
        )
        orchestrator = Orchestrator(
            Dispatcher([StaticRule()]), FakeVoiceProvider(),
            ActorRegistry([
                SquawkerActor(
                    "bird-dev", "bird", QueuedAudioOutput("route", backend)
                )
            ]),
            show_control=provider,
        )
        performance = asyncio.create_task(orchestrator.perform(
            Utterance("Do it", "bird", "test"), character, "bird-dev"
        ))
        await asyncio.sleep(0.01)
        self.assertEqual(provider.triggered, [])
        release.set()
        await performance
        self.assertEqual([action.name for action in provider.triggered], ["storm"])


if __name__ == "__main__":
    unittest.main()
