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
    VenueLoreRule,
)
from numan.lore import JsonLoreProvider
from numan.show_control import DrinkPresentationCatalog, DrinkPresentationRule


def build_character_dispatcher(
    *,
    policy: CharacterDispatchPolicy,
    exact_cache: ExactCacheRepository,
    response_pools: ResponsePoolRepository,
    structured_data: StructuredDataProvider,
    venue_lore: JsonLoreProvider | None = None,
    llm: LLMProvider,
    conversations: InMemoryConversationStore | None = None,
    drink_presentations: DrinkPresentationCatalog | None = None,
    chooser: Callable[[Sequence[str]], str] | None = None,
) -> Dispatcher:
    keyword = {"chooser": chooser} if chooser is not None else {}
    rules = [
        CharacterRoutineRule(policy, response_pools, **keyword),
        RepositoryExactCacheRule(exact_cache),
        RepositoryResponsePoolRule(response_pools, **keyword),
    ]
    if venue_lore is not None:
        rules.insert(0, VenueLoreRule(venue_lore, conversations))
    rules.extend((
        ProviderStructuredLookupRule(structured_data),
        ProviderLLMFallbackRule(llm, conversations, venue_lore=venue_lore),
    ))
    if drink_presentations is not None:
        rules.insert(0, DrinkPresentationRule(drink_presentations, **keyword))
    return Dispatcher(rules)


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
