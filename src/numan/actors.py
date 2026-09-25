"""Physical actor contracts and the audio-driven Squawker actor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .audio import AudioOutput, PlaybackResult
from .voice import AudioAsset


class Actor(Protocol):
    id: str
    character_id: str

    async def speak(self, asset: AudioAsset) -> PlaybackResult: ...
    async def stop(self) -> bool: ...
    def drain(self) -> None: ...


@dataclass(slots=True)
class SquawkerActor:
    """An audio-addressed actor whose controller generates physical motion."""

    id: str
    character_id: str
    output: AudioOutput

    async def speak(self, asset: AudioAsset) -> PlaybackResult:
        try:
            return await self.output.play(asset)
        finally:
            if asset.owned:
                asset.path.unlink(missing_ok=True)

    async def stop(self) -> bool:
        return await self.output.stop()

    def drain(self) -> None:
        self.output.drain()


class ActorRegistry:
    def __init__(self, actors=()) -> None:
        self._actors: dict[str, Actor] = {}
        for actor in actors:
            self.register(actor)

    def register(self, actor: Actor) -> None:
        if actor.id in self._actors:
            raise ValueError(f"duplicate actor id: {actor.id}")
        self._actors[actor.id] = actor

    def get(self, actor_id: str) -> Actor:
        try:
            return self._actors[actor_id]
        except KeyError as exc:
            raise LookupError(f"unknown actor: {actor_id}") from exc
