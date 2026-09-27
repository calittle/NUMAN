import unittest

from numan.actors import ActorRegistry, SquawkerActor
from numan.audio import QueuedAudioOutput
from numan.characters.dispatch import CharacterDispatcher, build_character_dispatcher
from numan.conversations import InMemoryConversationStore
from numan.engine.models import Character, Utterance
from numan.engine.policy import CharacterDispatchPolicy
from numan.engine.providers import NullStructuredDataProvider
from numan.engine.repositories import MappingExactCache, MappingResponsePools
from numan.orchestration import Orchestrator
from numan.testing import FakeAudioBackend, FakeVoiceProvider


class RecordingLLM:
    def __init__(self):
        self.calls = []

    async def complete(self, utterance, character, history=()):
        self.calls.append((character.id, tuple(turn.text for turn in history)))
        return f"{character.name} answers."


class MultiCharacterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.grog = Character("grog", "Captain Grog", "Dry.", "grog-voice")
        self.polly = Character("polly", "Polly", "Bright.", "polly-voice")
        self.llm = RecordingLLM()
        conversations = InMemoryConversationStore()

        def dispatcher(character_id, cached):
            return build_character_dispatcher(
                policy=CharacterDispatchPolicy(character_id, ()),
                exact_cache=MappingExactCache({"private phrase": cached}),
                response_pools=MappingResponsePools({}),
                structured_data=NullStructuredDataProvider(),
                llm=self.llm,
                conversations=conversations,
            )

        routing = CharacterDispatcher({
            "grog": dispatcher("grog", "Captain Grog's private answer."),
            "polly": dispatcher("polly", "Polly's private answer."),
        })
        self.voice = FakeVoiceProvider()
        self.grog_audio = FakeAudioBackend()
        self.polly_audio = FakeAudioBackend()
        actors = ActorRegistry([
            SquawkerActor(
                "grog-dev", "grog",
                QueuedAudioOutput("grog-route", self.grog_audio),
            ),
            SquawkerActor(
                "polly-dev", "polly",
                QueuedAudioOutput("polly-route", self.polly_audio),
            ),
        ])
        self.orchestrator = Orchestrator(
            routing, self.voice, actors, conversations=conversations
        )

    async def test_cache_voice_actor_and_route_are_character_specific(self):
        grog = await self.orchestrator.perform(
            Utterance("Private phrase", "grog", "shared"),
            self.grog,
            "grog-dev",
        )
        polly = await self.orchestrator.perform(
            Utterance("Private phrase", "polly", "shared"),
            self.polly,
            "polly-dev",
        )

        self.assertEqual(grog.plan.text, "Captain Grog's private answer.")
        self.assertEqual(polly.plan.text, "Polly's private answer.")
        self.assertEqual(self.voice.calls, [
            ("Captain Grog's private answer.", "grog-voice"),
            ("Polly's private answer.", "polly-voice"),
        ])
        self.assertEqual(self.grog_audio.plays[0][1], "grog-route")
        self.assertEqual(self.polly_audio.plays[0][1], "polly-route")

    async def test_same_conversation_id_does_not_share_history(self):
        await self.orchestrator.perform(
            Utterance("Captain Grog question", "grog", "shared"),
            self.grog,
            "grog-dev",
        )
        await self.orchestrator.perform(
            Utterance("Polly question", "polly", "shared"),
            self.polly,
            "polly-dev",
        )

        self.assertEqual(self.llm.calls[0], ("grog", ("Captain Grog question",)))
        self.assertEqual(self.llm.calls[1], ("polly", ("Polly question",)))


if __name__ == "__main__":
    unittest.main()
