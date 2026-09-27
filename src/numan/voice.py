"""Voice synthesis contracts and an Edge TTS/ffmpeg implementation."""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class AudioAsset:
    path: Path
    media_type: str = "audio/wav"
    owned: bool = False


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    id: str
    voice: str
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"
    ffmpeg_filter: str | None = None
    sample_rate: int = 24_000
    channels: int = 1


class VoiceProvider(Protocol):
    async def synthesize(self, text: str, profile_id: str) -> AudioAsset: ...


class VoiceProviderError(RuntimeError):
    pass


def tiki_console_filter(
    *,
    sample_rate: int,
    perch_pitch_semitones: float,
    barrel_chest_hz: int,
    barrel_chest_db: float,
    barrel_chest_width: float,
    beak_bite_hz: int,
    beak_bite_db: float,
    beak_bite_width: float,
    feather_sparkle_hz: int,
    feather_sparkle_db: float,
    coconut_radio_bits: int,
    rum_barrel_lufs: float,
) -> str:
    """Translate friendly character-voice controls into an ffmpeg filter graph."""
    pitch = f"{perch_pitch_semitones:g}"
    return (
        f"asetrate={sample_rate}*2^({pitch}/12),aresample={sample_rate},"
        f"atempo=1/2^({pitch}/12),"
        f"equalizer=f={barrel_chest_hz}:t=q:w={barrel_chest_width:g}:g={barrel_chest_db:g},"
        f"equalizer=f={beak_bite_hz}:t=q:w={beak_bite_width:g}:g={beak_bite_db:g},"
        f"equalizer=f={feather_sparkle_hz}:t=q:w=1:g={feather_sparkle_db:g},"
        f"acrusher=bits={coconut_radio_bits}:mode=log:aa=1,"
        f"loudnorm=I={rum_barrel_lufs:g}:LRA=7:TP=-1.5"
    )


class EdgeTTSVoiceProvider:
    """Render speech with edge-tts and optional ffmpeg character processing."""

    def __init__(
        self,
        profiles: Mapping[str, VoiceProfile],
        *,
        work_dir: str | Path | None = None,
        edge_tts_command: tuple[str, ...] | None = None,
        ffmpeg_command: str = "ffmpeg",
        command_timeout_s: float = 60.0,
    ) -> None:
        self._profiles = dict(profiles)
        self._work_dir = Path(work_dir or tempfile.gettempdir()) / "numan-voice"
        self._edge_tts_command = edge_tts_command or (sys.executable, "-m", "edge_tts")
        self._ffmpeg_command = ffmpeg_command
        self._command_timeout_s = command_timeout_s

    async def synthesize(self, text: str, profile_id: str) -> AudioAsset:
        if not text.strip():
            raise VoiceProviderError("cannot synthesize empty text")
        try:
            profile = self._profiles[profile_id]
        except KeyError as exc:
            raise VoiceProviderError(f"unknown voice profile: {profile_id}") from exc

        self._work_dir.mkdir(parents=True, exist_ok=True)
        stem = self._work_dir / uuid4().hex
        prompt = stem.with_suffix(".txt")
        raw = stem.with_suffix(".raw.wav")
        output = stem.with_suffix(".wav")
        prompt.write_text(text, encoding="utf-8")
        try:
            await self._run(
                *self._edge_tts_command,
                "--voice", profile.voice,
                f"--rate={profile.rate}",
                f"--volume={profile.volume}",
                f"--pitch={profile.pitch}",
                "--write-media", str(raw),
                "-f", str(prompt),
            )
            args = [self._ffmpeg_command, "-y", "-i", str(raw)]
            if profile.ffmpeg_filter:
                args.extend(["-af", profile.ffmpeg_filter])
            args.extend([
                "-ar", str(profile.sample_rate),
                "-ac", str(profile.channels),
                "-sample_fmt", "s16",
                str(output),
            ])
            await self._run(*args)
            if not output.exists() or output.stat().st_size == 0:
                raise VoiceProviderError("voice provider produced no output")
            return AudioAsset(output, owned=True)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            prompt.unlink(missing_ok=True)
            raw.unlink(missing_ok=True)

    async def _run(self, *argv: str) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise VoiceProviderError(f"required command not found: {argv[0]}") from exc
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._command_timeout_s
            )
        except asyncio.TimeoutError as exc:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            raise VoiceProviderError(
                f"command timed out after {self._command_timeout_s:g}s: {argv[0]}"
            ) from exc
        except asyncio.CancelledError:
            process.terminate()
            await process.wait()
            raise
        if process.returncode:
            detail = stderr.decode(errors="replace").strip()[:500]
            raise VoiceProviderError(
                f"command {shutil.which(argv[0]) or argv[0]} failed: {detail}"
            )
