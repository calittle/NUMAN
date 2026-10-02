"""Voice synthesis contracts and local/cloud implementations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol
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
    provider: str = "edge-tts"
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"
    ffmpeg_filter: str | None = None
    sample_rate: int = 24_000
    channels: int = 1
    model: Path | None = None
    model_config: Path | None = None
    voices: Path | None = None
    language: str = "en-us"
    speed: float = 1.0
    speaker: int | None = None
    length_scale: float = 1.0
    noise_scale: float = 0.667
    noise_w_scale: float = 0.8


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


class _LocalVoiceProvider(EdgeTTSVoiceProvider):
    """Shared resident-model and ffmpeg plumbing for offline providers."""

    def __init__(self, profiles: Mapping[str, VoiceProfile], **kwargs) -> None:
        super().__init__(profiles, **kwargs)
        self._lock = asyncio.Lock()

    async def _postprocess(self, raw: Path, output: Path, profile: VoiceProfile) -> None:
        args = [self._ffmpeg_command, "-y", "-i", str(raw)]
        filters = [f"aresample={profile.sample_rate}"]
        if profile.ffmpeg_filter:
            filters.append(profile.ffmpeg_filter)
        args.extend(["-af", ",".join(filters)])
        args.extend([
            "-ar", str(profile.sample_rate),
            "-ac", str(profile.channels),
            "-sample_fmt", "s16",
            str(output),
        ])
        await self._run(*args)
        if not output.exists() or output.stat().st_size == 0:
            raise VoiceProviderError("voice provider produced no output")

    def _profile(self, profile_id: str) -> VoiceProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise VoiceProviderError(f"unknown voice profile: {profile_id}") from exc


class PiperVoiceProvider(_LocalVoiceProvider):
    """Resident, fully local Piper ONNX synthesis."""

    def __init__(
        self,
        profiles: Mapping[str, VoiceProfile],
        *,
        voice_loader: Callable[[VoiceProfile], object] | None = None,
        synthesis_config_factory: Callable[[VoiceProfile], object] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(profiles, **kwargs)
        if voice_loader is None:
            try:
                from piper import PiperVoice, SynthesisConfig
            except ImportError as exc:
                raise VoiceProviderError(
                    "Piper is not installed (install NUMAN with the 'piper' extra)"
                ) from exc

            def voice_loader(profile: VoiceProfile):
                if profile.model is None:
                    raise VoiceProviderError(f"Piper profile {profile.id!r} has no model")
                return PiperVoice.load(
                    str(profile.model),
                    config_path=(str(profile.model_config) if profile.model_config else None),
                )

            synthesis_config_factory = lambda profile: SynthesisConfig(
                speaker_id=profile.speaker,
                length_scale=profile.length_scale,
                noise_scale=profile.noise_scale,
                noise_w_scale=profile.noise_w_scale,
            )
        self._voices = {key: voice_loader(profile) for key, profile in profiles.items()}
        self._synthesis_config_factory = synthesis_config_factory

    async def synthesize(self, text: str, profile_id: str) -> AudioAsset:
        if not text.strip():
            raise VoiceProviderError("cannot synthesize empty text")
        profile = self._profile(profile_id)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        stem = self._work_dir / uuid4().hex
        raw, output = stem.with_suffix(".raw.wav"), stem.with_suffix(".wav")
        try:
            async with self._lock:
                await asyncio.to_thread(self._render, text, profile, raw)
            await self._postprocess(raw, output, profile)
            return AudioAsset(output, owned=True)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            raw.unlink(missing_ok=True)

    def _render(self, text: str, profile: VoiceProfile, raw: Path) -> None:
        config = (
            self._synthesis_config_factory(profile)
            if self._synthesis_config_factory is not None else None
        )
        with wave.open(str(raw), "wb") as wav_file:
            kwargs = {"syn_config": config} if config is not None else {}
            self._voices[profile.id].synthesize_wav(text, wav_file, **kwargs)


class KokoroVoiceProvider(_LocalVoiceProvider):
    """Resident, fully local Kokoro ONNX synthesis."""

    def __init__(
        self,
        profiles: Mapping[str, VoiceProfile],
        *,
        model_loader: Callable[[VoiceProfile], object] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(profiles, **kwargs)
        if model_loader is None:
            try:
                from kokoro_onnx import Kokoro
            except ImportError as exc:
                raise VoiceProviderError(
                    "Kokoro is not installed (install NUMAN with the 'kokoro' extra)"
                ) from exc

            def model_loader(profile: VoiceProfile):
                if profile.model is None or profile.voices is None:
                    raise VoiceProviderError(
                        f"Kokoro profile {profile.id!r} requires model and voices files"
                    )
                return Kokoro(str(profile.model), str(profile.voices))

        # Sessions are shared when profiles point at the same model bundle.
        sessions: dict[tuple[Path | None, Path | None], object] = {}
        self._models = {}
        for key, profile in profiles.items():
            model_key = (profile.model, profile.voices)
            if model_key not in sessions:
                sessions[model_key] = model_loader(profile)
            self._models[key] = sessions[model_key]

    async def synthesize(self, text: str, profile_id: str) -> AudioAsset:
        if not text.strip():
            raise VoiceProviderError("cannot synthesize empty text")
        profile = self._profile(profile_id)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        stem = self._work_dir / uuid4().hex
        raw, output = stem.with_suffix(".raw.wav"), stem.with_suffix(".wav")
        try:
            async with self._lock:
                await asyncio.to_thread(self._render, text, profile, raw)
            await self._postprocess(raw, output, profile)
            return AudioAsset(output, owned=True)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            raw.unlink(missing_ok=True)

    def _render(self, text: str, profile: VoiceProfile, raw: Path) -> None:
        import numpy as np

        samples, sample_rate = self._models[profile.id].create(
            text, voice=profile.voice, speed=profile.speed, lang=profile.language
        )
        values = np.asarray(samples)
        if np.issubdtype(values.dtype, np.floating):
            values = np.clip(values, -1.0, 1.0)
            values = (values * 32767).astype(np.int16)
        else:
            values = values.astype(np.int16)
        with wave.open(str(raw), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(sample_rate))
            wav_file.writeframes(values.tobytes())


class RoutingVoiceProvider:
    """Route each configured profile to its selected synthesis engine."""

    def __init__(self, providers: Mapping[str, VoiceProvider], profiles: Mapping[str, str]):
        self._providers = dict(providers)
        self._profiles = dict(profiles)

    async def synthesize(self, text: str, profile_id: str) -> AudioAsset:
        try:
            provider_name = self._profiles[profile_id]
            provider = self._providers[provider_name]
        except KeyError as exc:
            raise VoiceProviderError(f"unknown voice profile: {profile_id}") from exc
        return await provider.synthesize(text, profile_id)


def default_voice_cache_dir() -> Path:
    """Return a native per-user cache location on Windows and macOS."""
    override = os.environ.get("NUMAN_TTS_CACHE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        return Path(root) / "NUMAN" / "cache" / "tts" if root else Path.home() / "AppData/Local/NUMAN/cache/tts"
    if sys.platform == "darwin":
        return Path.home() / "Library/Caches/NUMAN/tts"
    root = os.environ.get("XDG_CACHE_HOME")
    return (Path(root) if root else Path.home() / ".cache") / "numan/tts"


class CachedVoiceProvider:
    """Persist final, postprocessed WAVs for any configured provider."""

    def __init__(
        self,
        upstream: VoiceProvider,
        profiles: Mapping[str, VoiceProfile],
        *,
        cache_dir: str | Path | None = None,
    ) -> None:
        self._upstream = upstream
        self._profiles = dict(profiles)
        self._cache_dir = Path(cache_dir) if cache_dir else default_voice_cache_dir()
        self._locks: dict[str, asyncio.Lock] = {}
        self._fingerprints = {
            key: self._profile_fingerprint(profile) for key, profile in profiles.items()
        }

    async def synthesize(self, text: str, profile_id: str) -> AudioAsset:
        if not text.strip():
            raise VoiceProviderError("cannot synthesize empty text")
        try:
            fingerprint = self._fingerprints[profile_id]
        except KeyError as exc:
            raise VoiceProviderError(f"unknown voice profile: {profile_id}") from exc
        digest = hashlib.sha256(
            json.dumps(
                {"schema": 1, "profile": fingerprint, "text": text},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        destination = self._cache_dir / f"tts-{digest}.wav"
        if self._valid_wav(destination):
            return AudioAsset(destination, owned=False)
        lock = self._locks.setdefault(digest, asyncio.Lock())
        async with lock:
            if self._valid_wav(destination):
                return AudioAsset(destination, owned=False)
            rendered = await self._upstream.synthesize(text, profile_id)
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = self._cache_dir / f".{destination.name}-{uuid4().hex}.tmp"
            try:
                shutil.copyfile(rendered.path, temporary)
                if not self._valid_wav(temporary):
                    raise VoiceProviderError("voice provider produced an invalid WAV")
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
                if rendered.owned:
                    rendered.path.unlink(missing_ok=True)
            return AudioAsset(destination, owned=False)

    @staticmethod
    def _valid_wav(path: Path) -> bool:
        try:
            if not path.is_file() or path.stat().st_size <= 44:
                return False
            with wave.open(str(path), "rb") as wav_file:
                return wav_file.getnchannels() > 0 and wav_file.getframerate() > 0
        except (OSError, EOFError, wave.Error):
            return False

    @staticmethod
    def _profile_fingerprint(profile: VoiceProfile) -> dict[str, object]:
        def file_identity(path: Path | None) -> dict[str, object] | None:
            if path is None:
                return None
            try:
                stat = path.stat()
                return {"path": str(path.resolve()), "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns}
            except OSError:
                return {"path": str(path)}

        return {
            "provider": profile.provider,
            "voice": profile.voice,
            "rate": profile.rate,
            "volume": profile.volume,
            "pitch": profile.pitch,
            "ffmpeg_filter": profile.ffmpeg_filter,
            "sample_rate": profile.sample_rate,
            "channels": profile.channels,
            "model": file_identity(profile.model),
            "model_config": file_identity(profile.model_config),
            "voices": file_identity(profile.voices),
            "language": profile.language,
            "speed": profile.speed,
            "speaker": profile.speaker,
            "length_scale": profile.length_scale,
            "noise_scale": profile.noise_scale,
            "noise_w_scale": profile.noise_w_scale,
        }
