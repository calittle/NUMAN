"""Character-specific dispatch composition and routing."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from numan.conversations import InMemoryConversationStore
from numan.engine.dispatch import Dispatcher
from numan.engine.policy import CharacterDispatchPolicy
from numan.engine.providers import LLMProvider, StructuredDataProvider
from numan.engine.repositories import ExactCacheRepository, ResponsePoolRepository
from numan.engine.rules import (
    CharacterRoutineRule,
    ProviderLLMFallbackRule,
    ProviderStructuredLookupRule,
    RepositoryExactCacheRule,
    RepositoryResponsePoolRule,
)


def build_character_dispatcher(
    *,
    policy: CharacterDispatchPolicy,
    exact_cache: ExactCacheRepository,
    response_pools: ResponsePoolRepository,
    structured_data: StructuredDataProvider,
    llm: LLMProvider,
    conversations: InMemoryConversationStore | None = None,
    chooser: Callable[[Sequence[str]], str] | None = None,
) -> Dispatcher:
    keyword = {"chooser": chooser} if chooser is not None else {}
    return Dispatcher([
        CharacterRoutineRule(policy, response_pools, **keyword),
        RepositoryExactCacheRule(exact_cache),
        RepositoryResponsePoolRule(response_pools, **keyword),
        ProviderStructuredLookupRule(structured_data),
        ProviderLLMFallbackRule(llm, conversations),
    ])


class CharacterDispatcher:
    """Routes an utterance to the policy and repositories owned by its character."""

    def __init__(self, dispatchers: Mapping[str, Dispatcher]) -> None:
        self._dispatchers = dict(dispatchers)

    async def dispatch_with_trace(self, utterance, character, on_rule_start=None):
        try:
            dispatcher = self._dispatchers[character.id]
        except KeyError as exc:
            raise LookupError(f"no dispatcher for character {character.id!r}") from exc
        return await dispatcher.dispatch_with_trace(
            utterance, character, on_rule_start=on_rule_start
        )
