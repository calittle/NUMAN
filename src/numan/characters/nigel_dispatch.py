"""Composition root for Nigel-compatible, provider-independent dispatch."""

from __future__ import annotations

from numan.engine.dispatch import Dispatcher
from numan.engine.providers import LLMProvider, StructuredDataProvider
from numan.engine.repositories import ExactCacheRepository, ResponsePoolRepository
from numan.conversations import InMemoryConversationStore
from .dispatch import build_character_dispatcher

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
    return build_character_dispatcher(
        policy=NIGEL_DISPATCH_POLICY,
        exact_cache=exact_cache,
        response_pools=response_pools,
        structured_data=structured_data,
        llm=llm,
        conversations=conversations,
        chooser=chooser,
    )
