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
class VoiceConfig:
    id: str
    provider: str
    voice: str
    sample_rate: int
    channels: int
    ffmpeg_filter: str | None


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
class NumanConfig:
    default_character: str
    default_actor: str
    llm: LLMConfig
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
        for character in self.characters.values():
            if character.voice_profile not in self.voices:
                errors.append(
                    f"character {character.id!r} references unknown voice "
                    f"{character.voice_profile!r}"
                )
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
