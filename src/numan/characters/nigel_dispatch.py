"""Composition root for Nigel-compatible, provider-independent dispatch."""

from __future__ import annotations

from numan.engine.dispatch import Dispatcher
from numan.engine.providers import LLMProvider, StructuredDataProvider
from numan.engine.repositories import ExactCacheRepository, ResponsePoolRepository
from numan.conversations import InMemoryConversationStore
from numan.engine.rules import (
    CharacterRoutineRule,
    ProviderLLMFallbackRule,
    ProviderStructuredLookupRule,
    RepositoryExactCacheRule,
    RepositoryResponsePoolRule,
)

from .nigel import NIGEL_DISPATCH_POLICY


def build_nigel_dispatcher(
    *,
    exact_cache: ExactCacheRepository,
    response_pools: ResponsePoolRepository,
    structured_data: StructuredDataProvider,
    llm: LLMProvider,
    conversations: InMemoryConversationStore | None = None,
    chooser=None,
) -> Dispatcher:
    keyword = {"chooser": chooser} if chooser is not None else {}
    return Dispatcher(
        [
            CharacterRoutineRule(NIGEL_DISPATCH_POLICY, response_pools, **keyword),
            RepositoryExactCacheRule(exact_cache),
            RepositoryResponsePoolRule(response_pools, **keyword),
            ProviderStructuredLookupRule(structured_data),
            ProviderLLMFallbackRule(llm, conversations),
        ]
    )
