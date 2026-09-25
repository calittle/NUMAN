"""Application composition from validated configuration."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from pathlib import Path

from .actors import ActorRegistry, SquawkerActor
from .audio import QueuedAudioOutput, SoundDeviceBackend, SystemAudioBackend
from .characters.nigel_dispatch import build_nigel_dispatcher
from .configuration import ConfigurationError, NumanConfig
from .devices import list_audio_outputs
from .engine.models import Character
from .engine.providers import (
    FakeLLMProvider,
    NullStructuredDataProvider,
    OllamaConfig,
    OllamaLLMProvider,
    OpenAICompatibleConfig,
    OpenAICompatibleLLMProvider,
)
from .engine.repositories import JsonExactCache, JsonResponsePools
from .orchestration import Orchestrator
from .performance import NIGEL_STALLING_PLAN
from .testing import FakeAudioBackend, FakeVoiceProvider
from .voice import EdgeTTSVoiceProvider, VoiceProfile
from .conversations import InMemoryConversationStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Application:
    config: NumanConfig
    characters: dict[str, Character]
    actors: ActorRegistry
    orchestrator: Orchestrator


def build_application(config: NumanConfig, *, live: bool) -> Application:
    conversations = InMemoryConversationStore()
    characters = {
        item.id: Character(
            id=item.id,
            name=item.name,
            system_prompt=item.system_prompt,
            voice_profile=item.voice_profile,
            available_show_actions=item.show_actions,
        )
        for item in config.characters.values()
    }
    if set(characters) != {"nigel"}:
        raise ConfigurationError("this migration stage supports the Nigel dispatch policy only")

    pools = JsonResponsePools(PROJECT_ROOT / "data/nigel/response_pools.json")
    if config.llm.provider == "ollama":
        llm_provider = OllamaLLMProvider(OllamaConfig(
            base_url=config.llm.endpoint,
            model=config.llm.model,
        ))
    elif config.llm.provider == "openai-compatible":
        llm_provider = OpenAICompatibleLLMProvider(OpenAICompatibleConfig(
            endpoint=config.llm.endpoint,
            model=config.llm.model,
            api_key_env=config.llm.api_key_env,
        ))
    else:
        llm_provider = FakeLLMProvider("This is the development LLM fallback.")
    dispatcher = build_nigel_dispatcher(
        exact_cache=JsonExactCache(PROJECT_ROOT / "data/nigel/exact_cache.json"),
        response_pools=pools,
        structured_data=NullStructuredDataProvider(),
        llm=llm_provider,
        conversations=conversations,
    )

    if live:
        profiles = {
            voice.id: VoiceProfile(
                id=voice.id, voice=voice.voice,
                ffmpeg_filter=voice.ffmpeg_filter,
                sample_rate=voice.sample_rate, channels=voice.channels,
            )
            for voice in config.voices.values()
        }
        voice_provider = EdgeTTSVoiceProvider(profiles)
    else:
        voice_provider = FakeVoiceProvider()

    outputs = {}
    for route in config.audio_routes.values():
        if live and route.backend == "sounddevice":
            backend = SoundDeviceBackend(route.device)
        elif live:
            backend = SystemAudioBackend()
        else:
            backend = FakeAudioBackend()
        outputs[route.id] = QueuedAudioOutput(route.id, backend)

    actors = ActorRegistry(
        SquawkerActor(item.id, item.character, outputs[item.audio_route])
        for item in config.actors.values()
    )
    return Application(
        config=config, characters=characters, actors=actors,
        orchestrator=Orchestrator(
            dispatcher,
            voice_provider,
            actors,
            conversations=conversations,
            stalling=NIGEL_STALLING_PLAN,
        ),
    )


def live_environment_errors(config: NumanConfig) -> list[str]:
    errors = []
    if importlib.util.find_spec("edge_tts") is None:
        errors.append("edge-tts is not installed (install with: pip install -e '.[live]')")
    if shutil.which("ffmpeg") is None:
        errors.append("ffmpeg is not installed or not on PATH")
    available = {device.selector for device in list_audio_outputs()}
    for route in config.audio_routes.values():
        if route.backend == "sounddevice" and route.device not in available:
            errors.append(f"audio route {route.id!r} device is unavailable: {route.device}")
    return errors
