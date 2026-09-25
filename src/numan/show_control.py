"""Semantic show-control contracts; providers own choreography."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True, slots=True)
class ShowAction:
    name: str
    parameters: Mapping[str, object] = field(default_factory=dict)


class ShowControlProvider(Protocol):
    async def trigger(self, action: ShowAction) -> None: ...


class NullShowControlProvider:
    async def trigger(self, action: ShowAction) -> None:
        return None


class FakeLightORamaProvider:
    """Records semantic requests without implementing LOR choreography."""

    def __init__(self, allowed_actions=()) -> None:
        self.allowed_actions = frozenset(allowed_actions)
        self.triggered: list[ShowAction] = []

    async def trigger(self, action: ShowAction) -> None:
        if action.name not in self.allowed_actions:
            raise ValueError(f"show action is not allowed: {action.name}")
        self.triggered.append(action)
