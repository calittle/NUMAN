"""Conversation state scoped by character and conversation identifier."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class TurnRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    role: TurnRole
    text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationKey:
    character_id: str
    conversation_id: str


class InMemoryConversationStore:
    """Bounded in-process history; persistence can replace this contract later."""

    def __init__(self, max_turns: int = 20) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        self._max_turns = max_turns
        self._items: dict[ConversationKey, list[ConversationTurn]] = {}
        self._lock = asyncio.Lock()

    async def append(
        self, key: ConversationKey, role: TurnRole, text: str
    ) -> ConversationTurn:
        turn = ConversationTurn(role, text, datetime.now(UTC))
        async with self._lock:
            turns = self._items.setdefault(key, [])
            turns.append(turn)
            del turns[:-self._max_turns]
        return turn

    async def history(self, key: ConversationKey) -> tuple[ConversationTurn, ...]:
        async with self._lock:
            return tuple(self._items.get(key, ()))

    async def clear(self, key: ConversationKey) -> None:
        async with self._lock:
            self._items.pop(key, None)
