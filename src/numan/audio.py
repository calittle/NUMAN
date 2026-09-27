"""Audio-output contracts, queue semantics, and system playback adapter."""

from __future__ import annotations

import asyncio
import sys
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .voice import AudioAsset
from .devices import resolve_audio_device


class AudioBackend(Protocol):
    async def play(self, path: Path, route_id: str) -> None: ...
    async def stop(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PlaybackResult:
    route_id: str
    played: bool
    queue_wait_ms: float


class AudioOutput(Protocol):
    route_id: str

    async def play(self, asset: AudioAsset) -> PlaybackResult: ...
    async def stop(self) -> bool: ...
    def drain(self) -> None: ...


class QueuedAudioOutput:
    """Serialize one physical route and support orderly stop/drain."""

    def __init__(self, route_id: str, backend: AudioBackend) -> None:
        if not route_id.strip():
            raise ValueError("route_id must not be empty")
        self.route_id = route_id
        self._backend = backend
        self._lock = asyncio.Lock()
        self._generation = 0
        self._active = False

    async def play(self, asset: AudioAsset) -> PlaybackResult:
        loop = asyncio.get_running_loop()
        queued_at = loop.time()
        generation = self._generation
        async with self._lock:
            wait_ms = (loop.time() - queued_at) * 1000
            if generation != self._generation:
                return PlaybackResult(self.route_id, False, wait_ms)
            self._active = True
            try:
                await self._backend.play(asset.path, self.route_id)
            finally:
                self._active = False
            return PlaybackResult(self.route_id, True, wait_ms)

    async def stop(self) -> bool:
        self._generation += 1
        was_active = self._active
        await self._backend.stop()
        return was_active

    def drain(self) -> None:
        """Drop queued playback while allowing the active item to finish."""
        self._generation += 1


class SystemAudioBackend:
    """Safe system-default playback for macOS, Windows, and Linux.

    Named-device routing is intentionally rejected until a native endpoint-ID
    adapter is selected. A display name is not stable enough for show control.
    """

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None

    async def play(self, path: Path, route_id: str) -> None:
        if sys.platform == "darwin":
            argv = ("afplay", str(path))
        elif sys.platform == "win32":
            escaped = str(path).replace("'", "''")
            argv = (
                "powershell", "-NoProfile", "-Command",
                f"(New-Object Media.SoundPlayer '{escaped}').PlaySync()",
            )
        else:
            argv = ("paplay", str(path))
        self._process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await self._process.wait()
            if self._process.returncode:
                raise RuntimeError(
                    f"system audio player exited with status {self._process.returncode}"
                )
        except asyncio.CancelledError:
            if self._process.returncode is None:
                self._process.terminate()
                await self._process.wait()
            raise
        finally:
            self._process = None

    async def stop(self) -> None:
        process = self._process
        if process is not None and process.returncode is None:
            process.terminate()
            await process.wait()


class SoundDeviceBackend:
    """Device-addressable playback via PortAudio/CoreAudio/WASAPI."""

    def __init__(self, device_selector: str) -> None:
        self._selector = device_selector
        self._stop_requested = threading.Event()

    async def play(self, path: Path, route_id: str) -> None:
        await asyncio.to_thread(self._play_sync, path)

    def _play_sync(self, path: Path) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("install NUMAN with [live] for routed audio") from exc
        device_index = resolve_audio_device(self._selector)
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
        dtypes = {1: np.uint8, 2: np.int16, 4: np.int32}
        if sample_width not in dtypes:
            raise ValueError(f"unsupported WAV sample width: {sample_width}")
        samples = np.frombuffer(frames, dtype=dtypes[sample_width])
        if channels > 1:
            samples = samples.reshape(-1, channels)
        self._stop_requested.clear()
        with sd.OutputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype=dtypes[sample_width],
            device=device_index,
        ) as stream:
            for start in range(0, len(samples), 4096):
                if self._stop_requested.is_set():
                    break
                stream.write(samples[start:start + 4096])

    async def stop(self) -> None:
        self._stop_requested.set()
