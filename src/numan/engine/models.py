"""Data contracts shared by dispatch rules and future runtime adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class ResponseSource(StrEnum):
    """The dispatch layer that produced a response."""

    ROUTINE = "routine"
    EXACT_CACHE = "exact_cache"
    RESPONSE_POOL = "response_pool"
    STRUCTURED_LOOKUP = "structured_lookup"
    LLM_FALLBACK = "llm_fallback"


@dataclass(frozen=True, slots=True)
class Utterance:
    """Text understood from one activation, before dispatch."""

    text: str
    character_id: str
    conversation_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("utterance text must not be empty")
        if not self.character_id.strip():
            raise ValueError("character_id must not be empty")
        if not self.conversation_id.strip():
            raise ValueError("conversation_id must not be empty")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def normalized_text(self) -> str:
        return " ".join(self.text.casefold().split())


@dataclass(frozen=True, slots=True)
class Character:
    """Character-owned identity and behavior configuration.

    Physical actor and output-route details intentionally do not belong here.
    """

    id: str
    name: str
    system_prompt: str
    voice_profile: str
    available_show_actions: frozenset[str] = frozenset()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("character id and name must not be empty")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ResponsePlan:
    """Declarative result of dispatch; execution belongs to the runtime."""

    character_id: str
    conversation_id: str
    source: ResponseSource
    text: str | None = None
    audio_asset: str | None = None
    show_actions: tuple[str, ...] = ()
    show_action_delays: Mapping[str, float] = field(default_factory=dict)
    show_action_cooldowns: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text and not self.audio_asset and not self.show_actions:
            raise ValueError("a response plan must contain an observable action")
        object.__setattr__(
            self, "show_action_delays", MappingProxyType(dict(self.show_action_delays))
        )
        object.__setattr__(
            self,
            "show_action_cooldowns",
            MappingProxyType(dict(self.show_action_cooldowns)),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
