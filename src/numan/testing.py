"""Test and development fakes with no audio or network side effects."""

from __future__ import annotations

import asyncio
from pathlib import Path

from .voice import AudioAsset


class FakeVoiceProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def synthesize(self, text: str, profile_id: str) -> AudioAsset:
        self.calls.append((text, profile_id))
        return AudioAsset(Path(f"memory-{len(self.calls)}.wav"))


class FakeAudioBackend:
    def __init__(self, *, hold: asyncio.Event | None = None) -> None:
        self.hold = hold
        self.plays: list[tuple[Path, str]] = []
        self.active = 0
        self.max_active = 0
        self.stops = 0

    async def play(self, path: Path, route_id: str) -> None:
        self.plays.append((path, route_id))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.hold:
                await self.hold.wait()
        finally:
            self.active -= 1

    async def stop(self) -> None:
        self.stops += 1
        if self.hold:
            self.hold.set()
