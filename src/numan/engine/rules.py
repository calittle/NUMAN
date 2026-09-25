"""Reusable rules for the initial fast-first dispatch chain."""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field

from .models import Character, ResponsePlan, ResponseSource, Utterance
from .normalization import extract_drink_query, routine_text, stable_text
from .policy import CharacterDispatchPolicy
from .providers import LLMProvider, StructuredDataProvider
from numan.conversations import ConversationKey, InMemoryConversationStore
from .repositories import ExactCacheRepository, ResponsePoolRepository

ResponseFactory = Callable[[Utterance, Character], ResponsePlan | Awaitable[ResponsePlan]]
Lookup = Callable[[Utterance, Character], str | None | Awaitable[str | None]]
Fallback = Callable[[Utterance, Character], str | Awaitable[str]]


async def _resolve(value):
    if hasattr(value, "__await__"):
        return await value
    return value


def _plan(
    utterance: Utterance,
    source: ResponseSource,
    *,
    text: str | None = None,
    audio_asset: str | None = None,
    show_actions: tuple[str, ...] = (),
    metadata: Mapping[str, object] | None = None,
) -> ResponsePlan:
    return ResponsePlan(
        character_id=utterance.character_id,
        conversation_id=utterance.conversation_id,
        source=source,
        text=text,
        audio_asset=audio_asset,
        show_actions=show_actions,
        metadata=metadata or {},
    )


@dataclass(slots=True)
class RoutineRule:
    routines: Sequence[tuple[str, Callable[[str], bool], ResponseFactory]]
    name: str = "routines"

    async def evaluate(self, utterance: Utterance, character: Character):
        for routine_name, matches, factory in self.routines:
            if matches(utterance.normalized_text):
                plan = await _resolve(factory(utterance, character))
                return ResponsePlan(
                    character_id=plan.character_id,
                    conversation_id=plan.conversation_id,
                    source=ResponseSource.ROUTINE,
                    text=plan.text,
                    audio_asset=plan.audio_asset,
                    show_actions=plan.show_actions,
                    metadata={**plan.metadata, "routine": routine_name},
                )
        return None


@dataclass(slots=True)
class ExactCacheRule:
    entries: Mapping[str, str]
    name: str = "exact_cache"

    async def evaluate(self, utterance: Utterance, character: Character):
        text = self.entries.get(utterance.normalized_text)
        return _plan(utterance, ResponseSource.EXACT_CACHE, text=text) if text else None


@dataclass(slots=True)
class ResponsePoolRule:
    pools: Mapping[str, Sequence[str]]
    matcher: Callable[[str], str | None]
    chooser: Callable[[Sequence[str]], str] = field(default=random.choice)
    name: str = "response_pool"

    async def evaluate(self, utterance: Utterance, character: Character):
        pool_name = self.matcher(utterance.normalized_text)
        entries = self.pools.get(pool_name, ()) if pool_name else ()
        if not entries:
            return None
        return _plan(
            utterance,
            ResponseSource.RESPONSE_POOL,
            text=self.chooser(entries),
            metadata={"pool": pool_name},
        )


@dataclass(slots=True)
class StructuredLookupRule:
    lookup: Lookup
    name: str = "structured_lookup"

    async def evaluate(self, utterance: Utterance, character: Character):
        text = await _resolve(self.lookup(utterance, character))
        return _plan(utterance, ResponseSource.STRUCTURED_LOOKUP, text=text) if text else None


@dataclass(slots=True)
class LLMFallbackRule:
    complete: Fallback
    name: str = "llm_fallback"

    async def evaluate(self, utterance: Utterance, character: Character):
        text = await _resolve(self.complete(utterance, character))
        return _plan(utterance, ResponseSource.LLM_FALLBACK, text=text)


@dataclass(slots=True)
class CharacterRoutineRule:
    policy: CharacterDispatchPolicy
    pools: ResponsePoolRepository
    chooser: Callable[[Sequence[str]], str] = field(default=random.choice)
    name: str = "routines"

    async def evaluate(self, utterance: Utterance, character: Character):
        text = routine_text(utterance.text)
        for routine in self.policy.routines:
            match = routine.pattern.search(text)
            if not match:
                continue
            if routine.pool:
                entries = self.pools.entries(routine.pool)
                if not entries:
                    continue
                response = self.chooser(entries)
            elif routine.response_template:
                response = routine.response_template.format(**match.groupdict())
            else:
                continue
            return _plan(
                utterance,
                ResponseSource.ROUTINE,
                text=response,
                show_actions=routine.show_actions,
                metadata={"routine": routine.name, "pool": routine.pool},
            )
        return None


@dataclass(slots=True)
class RepositoryExactCacheRule:
    repository: ExactCacheRepository
    name: str = "exact_cache"

    async def evaluate(self, utterance: Utterance, character: Character):
        key = extract_drink_query(utterance.text) or stable_text(utterance.text)
        text = self.repository.lookup(key)
        return _plan(utterance, ResponseSource.EXACT_CACHE, text=text) if text else None


@dataclass(slots=True)
class RepositoryResponsePoolRule:
    repository: ResponsePoolRepository
    chooser: Callable[[Sequence[str]], str] = field(default=random.choice)
    name: str = "response_pool"

    async def evaluate(self, utterance: Utterance, character: Character):
        match = self.repository.match(stable_text(utterance.text))
        if match is None:
            return None
        pool_name, entries = match
        return _plan(
            utterance,
            ResponseSource.RESPONSE_POOL,
            text=self.chooser(entries),
            metadata={"pool": pool_name},
        )


@dataclass(slots=True)
class ProviderStructuredLookupRule:
    provider: StructuredDataProvider
    name: str = "structured_lookup"

    async def evaluate(self, utterance: Utterance, character: Character):
        query = extract_drink_query(utterance.text)
        if query is None:
            return None
        text = await self.provider.lookup(query, character)
        return _plan(utterance, ResponseSource.STRUCTURED_LOOKUP, text=text) if text else None


@dataclass(slots=True)
class ProviderLLMFallbackRule:
    provider: LLMProvider
    conversations: InMemoryConversationStore | None = None
    name: str = "llm_fallback"

    async def evaluate(self, utterance: Utterance, character: Character):
        history = ()
        if self.conversations is not None:
            history = await self.conversations.history(
                ConversationKey(character.id, utterance.conversation_id)
            )
        text = await self.provider.complete(utterance, character, history)
        return _plan(utterance, ResponseSource.LLM_FALLBACK, text=text)
