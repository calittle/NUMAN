import unittest

from numan.actors import ActorRegistry, SquawkerActor
from numan.audio import QueuedAudioOutput
from numan.conversations import ConversationKey, InMemoryConversationStore, TurnRole
from numan.engine.dispatch import Dispatcher
from numan.engine.models import Character, ResponsePlan, ResponseSource, Utterance
from numan.engine.rules import ProviderLLMFallbackRule
from numan.engine.providers import FakeLLMProvider
from numan.orchestration import Orchestrator
from numan.show_control import FakeLightORamaProvider
from numan.testing import FakeAudioBackend, FakeVoiceProvider
from numan.application import PROJECT_ROOT, build_application
from numan.configuration import load_config


CHARACTER = Character(
    "captain", "Captain", "Be brief.", "voice",
    available_show_actions=frozenset({"storm"}),
)


class StaticRule:
    name = "static"

    def __init__(self, actions=()):
        self.actions = actions

    async def evaluate(self, utterance, character):
        return ResponsePlan(
            character.id, utterance.conversation_id, ResponseSource.ROUTINE,
            text="Answer", show_actions=self.actions,
        )


def actor():
    return SquawkerActor(
        "bird", "captain", QueuedAudioOutput("route", FakeAudioBackend())
    )


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_histories_are_scoped_and_bounded(self):
        store = InMemoryConversationStore(max_turns=2)
        first = ConversationKey("a", "same")
        second = ConversationKey("b", "same")
        await store.append(first, TurnRole.USER, "one")
        await store.append(first, TurnRole.ASSISTANT, "two")
        await store.append(first, TurnRole.USER, "three")
        await store.append(second, TurnRole.USER, "other")
        self.assertEqual([turn.text for turn in await store.history(first)], ["two", "three"])
        self.assertEqual([turn.text for turn in await store.history(second)], ["other"])

    async def test_llm_receives_current_scoped_history(self):
        store = InMemoryConversationStore()
        llm = FakeLLMProvider("Reply")
        dispatcher = Dispatcher([ProviderLLMFallbackRule(llm, store)])
        registered = actor()
        orchestrator = Orchestrator(
            dispatcher, FakeVoiceProvider(), ActorRegistry([registered]),
            conversations=store,
        )
        await orchestrator.perform(
            Utterance("First question", "captain", "session"), CHARACTER, "bird"
        )
        await orchestrator.perform(
            Utterance("Follow up", "captain", "session"), CHARACTER, "bird"
        )
        self.assertEqual(
            [turn.text for turn in llm.histories[1]],
            ["First question", "Reply", "Follow up"],
        )


class ShowControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_nigel_routine_triggers_semantic_storm(self):
        application = build_application(
            load_config(PROJECT_ROOT / "config/numan.toml"), live=False
        )
        result = await application.orchestrator.perform(
            Utterance("Bring on a storm", "nigel", "show-test"),
            application.characters["nigel"],
            "nigel-dev",
        )
        self.assertEqual(result.plan.show_actions, ("storm",))
        self.assertEqual(
            [action.name for action in application.show_control.triggered],
            ["storm"],
        )

    async def test_semantic_action_reaches_provider(self):
        provider = FakeLightORamaProvider({"storm"})
        registered = actor()
        orchestrator = Orchestrator(
            Dispatcher([StaticRule(("storm",))]),
            FakeVoiceProvider(), ActorRegistry([registered]),
            show_control=provider,
        )
        await orchestrator.perform(
            Utterance("Do it", "captain", "session"), CHARACTER, "bird"
        )
        self.assertEqual([action.name for action in provider.triggered], ["storm"])

    async def test_character_cannot_escape_action_allowlist(self):
        registered = actor()
        orchestrator = Orchestrator(
            Dispatcher([StaticRule(("blackout",))]),
            FakeVoiceProvider(), ActorRegistry([registered]),
            show_control=FakeLightORamaProvider({"blackout"}),
        )
        with self.assertRaisesRegex(ValueError, "cannot trigger"):
            await orchestrator.perform(
                Utterance("Do it", "captain", "session"), CHARACTER, "bird"
            )


if __name__ == "__main__":
    unittest.main()
