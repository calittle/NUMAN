"""Typed application configuration and referential validation."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CharacterConfig:
    id: str
    name: str
    system_prompt: str
    voice_profile: str
    show_actions: frozenset[str]


@dataclass(frozen=True, slots=True)
class TikiConsoleConfig:
    perch_pitch_semitones: float
    beak_bite_hz: int
    beak_bite_db: float
    beak_bite_width: float
    feather_sparkle_hz: int
    feather_sparkle_db: float
    coconut_radio_bits: int
    rum_barrel_lufs: float


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    id: str
    provider: str
    voice: str
    sample_rate: int
    channels: int
    ffmpeg_filter: str | None
    tiki_console: TikiConsoleConfig | None


@dataclass(frozen=True, slots=True)
class AudioRouteConfig:
    id: str
    backend: str
    device: str


@dataclass(frozen=True, slots=True)
class ActorConfig:
    id: str
    type: str
    character: str
    audio_route: str


@dataclass(frozen=True, slots=True)
class LLMConfig:
    provider: str
    endpoint: str
    model: str
    api_key_env: str


@dataclass(frozen=True, slots=True)
class STTConfig:
    provider: str
    model: str
    command: str
    endpoint: str
    api_key_env: str
    language: str
    prompt: str


@dataclass(frozen=True, slots=True)
class MicrophoneConfig:
    device: str
    sample_rate: int
    channels: int


@dataclass(frozen=True, slots=True)
class WakeTargetConfig:
    id: str
    phrases: tuple[str, ...]
    character: str
    actor: str


@dataclass(frozen=True, slots=True)
class WakeConfig:
    enabled: bool
    model_dir: str
    threshold: float
    score: float
    targets: Mapping[str, WakeTargetConfig]


@dataclass(frozen=True, slots=True)
class NumanConfig:
    default_character: str
    default_actor: str
    llm: LLMConfig
    stt: STTConfig
    microphone: MicrophoneConfig
    wake: WakeConfig
    characters: Mapping[str, CharacterConfig]
    voices: Mapping[str, VoiceConfig]
    audio_routes: Mapping[str, AudioRouteConfig]
    actors: Mapping[str, ActorConfig]

    def validate(self) -> None:
        errors: list[str] = []
        if self.default_character not in self.characters:
            errors.append(f"unknown default character {self.default_character!r}")
        if self.default_actor not in self.actors:
            errors.append(f"unknown default actor {self.default_actor!r}")
        elif (
            self.default_character in self.characters
            and self.actors[self.default_actor].character != self.default_character
        ):
            errors.append("default actor does not represent the default character")
        for character in self.characters.values():
            if character.voice_profile not in self.voices:
                errors.append(
                    f"character {character.id!r} references unknown voice "
                    f"{character.voice_profile!r}"
                )
        for voice in self.voices.values():
            console = voice.tiki_console
            if console is not None and voice.ffmpeg_filter:
                errors.append(
                    f"voice {voice.id!r} cannot use both tiki_console and ffmpeg_filter"
                )
            if console is not None:
                if not -12 <= console.perch_pitch_semitones <= 12:
                    errors.append(f"voice {voice.id!r} perch pitch must be -12 to 12")
                if not 100 <= console.beak_bite_hz <= 12_000:
                    errors.append(f"voice {voice.id!r} beak bite frequency is out of range")
                if not -30 <= console.beak_bite_db <= 30:
                    errors.append(f"voice {voice.id!r} beak bite must be -30 to 30 dB")
                if not 0.1 <= console.beak_bite_width <= 10:
                    errors.append(f"voice {voice.id!r} beak bite width must be 0.1 to 10")
                if not 100 <= console.feather_sparkle_hz <= 12_000:
                    errors.append(f"voice {voice.id!r} feather sparkle frequency is out of range")
                if not -30 <= console.feather_sparkle_db <= 30:
                    errors.append(f"voice {voice.id!r} feather sparkle must be -30 to 30 dB")
                if not 2 <= console.coconut_radio_bits <= 16:
                    errors.append(f"voice {voice.id!r} coconut radio must be 2 to 16 bits")
                if not -30 <= console.rum_barrel_lufs <= -5:
                    errors.append(f"voice {voice.id!r} rum barrel must be -30 to -5 LUFS")
        for actor in self.actors.values():
            if actor.character not in self.characters:
                errors.append(
                    f"actor {actor.id!r} references unknown character {actor.character!r}"
                )
            if actor.audio_route not in self.audio_routes:
                errors.append(
                    f"actor {actor.id!r} references unknown route {actor.audio_route!r}"
                )
            if actor.type != "squawker":
                errors.append(f"actor {actor.id!r} has unsupported type {actor.type!r}")
        for route in self.audio_routes.values():
            if route.backend not in {"system-default", "sounddevice"}:
                errors.append(f"route {route.id!r} has unsupported backend {route.backend!r}")
            if route.backend == "system-default" and route.device != "system-default":
                errors.append(
                    f"route {route.id!r}: system-default backend cannot select {route.device!r}"
                )
        if self.llm.provider not in {"fake", "ollama", "openai-compatible"}:
            errors.append(f"unsupported LLM provider {self.llm.provider!r}")
        if self.llm.provider == "ollama":
            if not self.llm.endpoint or not self.llm.model:
                errors.append("Ollama LLM requires endpoint and model")
        if self.llm.provider == "openai-compatible":
            if not self.llm.endpoint or not self.llm.model:
                errors.append("openai-compatible LLM requires endpoint and model")
        if self.stt.provider not in {"whisper-cpp", "deepgram"}:
            errors.append(f"unsupported STT provider {self.stt.provider!r}")
        if self.stt.provider == "whisper-cpp" and (
            not self.stt.command or not self.stt.model
        ):
            errors.append("whisper-cpp STT requires command and model")
        if self.stt.provider == "deepgram" and (
            not self.stt.endpoint or not self.stt.api_key_env
        ):
            errors.append("Deepgram STT requires endpoint and API key environment name")
        if self.microphone.sample_rate <= 0 or self.microphone.channels != 1:
            errors.append("microphone requires a positive sample rate and one channel")
        phrases: dict[str, str] = {}
        for target in self.wake.targets.values():
            if target.character not in self.characters:
                errors.append(
                    f"wake target {target.id!r} references unknown character "
                    f"{target.character!r}"
                )
            if target.actor not in self.actors:
                errors.append(
                    f"wake target {target.id!r} references unknown actor {target.actor!r}"
                )
            elif self.actors[target.actor].character != target.character:
                errors.append(
                    f"wake target {target.id!r} actor does not represent "
                    f"{target.character!r}"
                )
            if not target.phrases:
                errors.append(f"wake target {target.id!r} has no phrases")
            for phrase in target.phrases:
                normalized = " ".join(phrase.casefold().split())
                if not normalized:
                    errors.append(f"wake target {target.id!r} has an empty phrase")
                elif normalized in phrases:
                    errors.append(
                        f"duplicate wake phrase {phrase!r} in {target.id!r} "
                        f"and {phrases[normalized]!r}"
                    )
                else:
                    phrases[normalized] = target.id
        if self.wake.enabled and not self.wake.targets:
            errors.append("wake detection is enabled but has no targets")
        if not 0 < self.wake.threshold <= 1 or self.wake.score <= 0:
            errors.append("wake threshold must be in (0, 1] and score must be positive")
        if errors:
            raise ConfigurationError("; ".join(errors))


def load_config(path: str | Path) -> NumanConfig:
    source = Path(path)
    try:
        raw = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"cannot read {source}: {exc}") from exc
    try:
        runtime = raw["runtime"]
        llm_raw = raw["llm"]
        stt_raw = raw["stt"]
        microphone_raw = raw["microphone"]
        wake_raw = raw["wake"]
        characters = {
            key: CharacterConfig(
                id=key,
                name=_string(value, "name"),
                system_prompt=_string(value, "system_prompt"),
                voice_profile=_string(value, "voice_profile"),
                show_actions=frozenset(value.get("show_actions", [])),
            )
            for key, value in _table(raw, "characters").items()
        }
        voices = {
            key: VoiceConfig(
                id=key,
                provider=_string(value, "provider"),
                voice=_string(value, "voice"),
                sample_rate=int(value.get("sample_rate", 24_000)),
                channels=int(value.get("channels", 1)),
                ffmpeg_filter=value.get("ffmpeg_filter"),
                tiki_console=_tiki_console(value.get("tiki_console")),
            )
            for key, value in _table(raw, "voices").items()
        }
        routes = {
            key: AudioRouteConfig(
                id=key,
                backend=_string(value, "backend"),
                device=_string(value, "device"),
            )
            for key, value in _table(raw, "audio_routes").items()
        }
        actors = {
            key: ActorConfig(
                id=key,
                type=_string(value, "type"),
                character=_string(value, "character"),
                audio_route=_string(value, "audio_route"),
            )
            for key, value in _table(raw, "actors").items()
        }
        config = NumanConfig(
            default_character=_string(runtime, "default_character"),
            default_actor=_string(runtime, "default_actor"),
            llm=LLMConfig(
                provider=_string(llm_raw, "provider"),
                endpoint=str(llm_raw.get("endpoint", "")),
                model=str(llm_raw.get("model", "")),
                api_key_env=_string(llm_raw, "api_key_env"),
            ),
            stt=STTConfig(
                provider=_string(stt_raw, "provider"),
                model=_string(stt_raw, "model"),
                command=_string(stt_raw, "command"),
                endpoint=_string(stt_raw, "endpoint"),
                api_key_env=_string(stt_raw, "api_key_env"),
                language=_string(stt_raw, "language"),
                prompt=str(stt_raw.get("prompt", "")),
            ),
            microphone=MicrophoneConfig(
                device=_string(microphone_raw, "device"),
                sample_rate=int(microphone_raw.get("sample_rate", 16_000)),
                channels=int(microphone_raw.get("channels", 1)),
            ),
            wake=WakeConfig(
                enabled=bool(wake_raw.get("enabled", False)),
                model_dir=_string(wake_raw, "model_dir"),
                threshold=float(wake_raw.get("threshold", 0.20)),
                score=float(wake_raw.get("score", 1.0)),
                targets={
                    key: WakeTargetConfig(
                        id=key,
                        phrases=tuple(value.get("phrases", ())),
                        character=_string(value, "character"),
                        actor=_string(value, "actor"),
                    )
                    for key, value in _table(wake_raw, "targets").items()
                },
            ),
            characters=characters,
            voices=voices,
            audio_routes=routes,
            actors=actors,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"invalid {source}: {exc}") from exc
    config.validate()
    return config


def _table(raw: Mapping[str, Any], key: str) -> Mapping[str, Mapping[str, Any]]:
    value = raw[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be a table")
    return value


def _string(raw: Mapping[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _tiki_console(raw: Any) -> TikiConsoleConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TypeError("tiki_console must be a table")
    return TikiConsoleConfig(
        perch_pitch_semitones=float(raw["perch_pitch_semitones"]),
        beak_bite_hz=int(raw["beak_bite_hz"]),
        beak_bite_db=float(raw["beak_bite_db"]),
        beak_bite_width=float(raw["beak_bite_width"]),
        feather_sparkle_hz=int(raw["feather_sparkle_hz"]),
        feather_sparkle_db=float(raw["feather_sparkle_db"]),
        coconut_radio_bits=int(raw["coconut_radio_bits"]),
        rum_barrel_lufs=float(raw["rum_barrel_lufs"]),
    )
