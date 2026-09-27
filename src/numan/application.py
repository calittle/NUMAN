"""Application composition from validated configuration."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from pathlib import Path

from .actors import ActorRegistry, SquawkerActor
from .audio import QueuedAudioOutput, SoundDeviceBackend, SystemAudioBackend
from .characters.dispatch import CharacterDispatcher, build_character_dispatcher
from .characters.grog import GROG_DISPATCH_POLICY
from .characters.polly import POLLY_DISPATCH_POLICY
from .configuration import ConfigurationError, NumanConfig
from .devices import list_audio_outputs
from .engine.models import Character
from .engine.providers import (
    FakeLLMProvider,
    OllamaConfig,
    OllamaLLMProvider,
    OpenAICompatibleConfig,
    OpenAICompatibleLLMProvider,
)
from .engine.repositories import JsonExactCache, JsonResponsePools
from .orchestration import Orchestrator
from .performance import GROG_STALLING_PLAN, POLLY_STALLING_PLAN
from .recipes import JsonCocktailProvider
from .show_control import (
    DrinkPresentationCatalog,
    FakeLightORamaProvider,
    LightORamaOSCTriggerProvider,
    LORTrigger,
    NullShowControlProvider,
    ShowActionScheduler,
)
from .testing import FakeAudioBackend, FakeVoiceProvider
from .transcription import (
    DeepgramConfig,
    DeepgramSTTProvider,
    STTProvider,
    WhisperCppConfig,
    WhisperCppSTTProvider,
)
from .voice import EdgeTTSVoiceProvider, VoiceProfile, tiki_console_filter
from .wake import SherpaWakeConfig, WakeRegistry, WakeTarget
from .conversations import InMemoryConversationStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Application:
    config: NumanConfig
    characters: dict[str, Character]
    actors: ActorRegistry
    orchestrator: Orchestrator
    show_control: object
    show_scheduler: ShowActionScheduler


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
    policies = {
        "grog": GROG_DISPATCH_POLICY,
        "polly": POLLY_DISPATCH_POLICY,
    }
    unsupported = set(characters) - set(policies)
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ConfigurationError(f"no dispatch policy configured for: {names}")
    structured_data = JsonCocktailProvider(
        PROJECT_ROOT / "data/cocktails/recipes.json"
    )
    drink_presentations = DrinkPresentationCatalog(
        PROJECT_ROOT / "data/show/drink_presentations.json"
    )
    for presentation in drink_presentations.items:
        if presentation.show_action not in config.show_control.allowed_actions:
            raise ConfigurationError(
                f"drink {presentation.drink_id!r} references unavailable show action "
                f"{presentation.show_action!r}"
            )
        for character_id in presentation.responses:
            if character_id not in characters:
                raise ConfigurationError(
                    f"drink {presentation.drink_id!r} references unknown character "
                    f"{character_id!r}"
                )
            if presentation.show_action not in characters[character_id].available_show_actions:
                raise ConfigurationError(
                    f"character {character_id!r} is not allowed to present "
                    f"{presentation.drink_id!r}"
                )
    dispatcher = CharacterDispatcher({
        character_id: build_character_dispatcher(
            policy=policies[character_id],
            exact_cache=JsonExactCache(
                PROJECT_ROOT / f"data/{character_id}/exact_cache.json"
            ),
            response_pools=JsonResponsePools(
                PROJECT_ROOT / f"data/{character_id}/response_pools.json"
            ),
            structured_data=structured_data,
            llm=llm_provider,
            conversations=conversations,
            drink_presentations=drink_presentations,
        )
        for character_id in characters
    })

    if live:
        profiles = {
            voice.id: VoiceProfile(
                id=voice.id, voice=voice.voice,
                rate=voice.rate, volume=voice.volume, pitch=voice.pitch,
                ffmpeg_filter=(
                    tiki_console_filter(
                        sample_rate=voice.sample_rate,
                        perch_pitch_semitones=voice.tiki_console.perch_pitch_semitones,
                        barrel_chest_hz=voice.tiki_console.barrel_chest_hz,
                        barrel_chest_db=voice.tiki_console.barrel_chest_db,
                        barrel_chest_width=voice.tiki_console.barrel_chest_width,
                        beak_bite_hz=voice.tiki_console.beak_bite_hz,
                        beak_bite_db=voice.tiki_console.beak_bite_db,
                        beak_bite_width=voice.tiki_console.beak_bite_width,
                        feather_sparkle_hz=voice.tiki_console.feather_sparkle_hz,
                        feather_sparkle_db=voice.tiki_console.feather_sparkle_db,
                        coconut_radio_bits=voice.tiki_console.coconut_radio_bits,
                        rum_barrel_lufs=voice.tiki_console.rum_barrel_lufs,
                    )
                    if voice.tiki_console is not None else voice.ffmpeg_filter
                ),
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
    if live and config.show_control.provider == "lor-osc-trigger":
        show_control = LightORamaOSCTriggerProvider(
            config.show_control.host,
            config.show_control.port,
            {
                action: LORTrigger(item.network, item.unit, item.circuit)
                for action, item in config.show_control.triggers.items()
            },
        )
    elif config.show_control.provider in {"fake", "lor-osc-trigger"}:
        show_control = FakeLightORamaProvider(config.show_control.allowed_actions)
    else:
        show_control = NullShowControlProvider()
    show_scheduler = ShowActionScheduler(show_control)
    return Application(
        config=config, characters=characters, actors=actors,
        show_control=show_control,
        show_scheduler=show_scheduler,
        orchestrator=Orchestrator(
            dispatcher,
            voice_provider,
            actors,
            conversations=conversations,
            show_scheduler=show_scheduler,
            stalling={"grog": GROG_STALLING_PLAN, "polly": POLLY_STALLING_PLAN},
        ),
    )


def resolve_actor_id(
    config: NumanConfig, character_id: str, requested_actor_id: str | None
) -> str:
    """Choose the explicit actor or the sole actor representing a character."""
    if requested_actor_id is not None:
        return requested_actor_id
    if character_id == config.default_character:
        return config.default_actor
    matches = [item.id for item in config.actors.values() if item.character == character_id]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ConfigurationError(f"no actor represents character {character_id!r}")
    raise ConfigurationError(
        f"character {character_id!r} has multiple actors; select one with --actor"
    )


def build_stt_provider(config: NumanConfig) -> STTProvider:
    if config.stt.provider == "whisper-cpp":
        model = Path(config.stt.model)
        if not model.is_absolute():
            model = PROJECT_ROOT / model
        return WhisperCppSTTProvider(WhisperCppConfig(
            model_path=model,
            command=config.stt.command,
            language=config.stt.language,
            prompt=config.stt.prompt,
        ))
    return DeepgramSTTProvider(DeepgramConfig(
        endpoint=config.stt.endpoint,
        api_key_env=config.stt.api_key_env,
    ))


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


def stt_environment_errors(config: NumanConfig) -> list[str]:
    if config.stt.provider == "whisper-cpp":
        provider = build_stt_provider(config)
        return provider.status_errors()
    return []


def build_wake_registry(config: NumanConfig) -> WakeRegistry:
    return WakeRegistry(tuple(
        WakeTarget(item.id, item.phrases, item.character, item.actor)
        for item in config.wake.targets.values()
    ))


def build_wake_config(config: NumanConfig) -> SherpaWakeConfig:
    model_dir = Path(config.wake.model_dir)
    if not model_dir.is_absolute():
        model_dir = PROJECT_ROOT / model_dir
    return SherpaWakeConfig(
        model_dir=model_dir,
        threshold=config.wake.threshold,
        score=config.wake.score,
        sample_rate=config.microphone.sample_rate,
    )
