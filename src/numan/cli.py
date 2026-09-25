"""NUMAN command line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
from pathlib import Path

from .application import (
    PROJECT_ROOT,
    build_application,
    build_stt_provider,
    live_environment_errors,
    stt_environment_errors,
)
from .configuration import ConfigurationError, load_config
from .devices import list_audio_inputs, list_audio_outputs
from .engine.models import Utterance
from .engine.providers import LLMProviderError, OllamaConfig, OllamaLLMProvider
from .transcription import MicrophoneRecorder, TranscriptionError, WhisperCppSTTProvider

DEFAULT_CONFIG = PROJECT_ROOT / "config/numan.toml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="numan")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    devices = subparsers.add_parser("devices", help="inspect audio devices")
    device_commands = devices.add_subparsers(dest="devices_command", required=True)
    device_commands.add_parser("list", help="list output devices")
    device_commands.add_parser("inputs", help="list microphone devices")

    config = subparsers.add_parser("config", help="validate configuration")
    validate = config.add_subparsers(dest="config_command", required=True).add_parser("validate")
    validate.add_argument("--live", action="store_true", help="also check live dependencies")

    llm = subparsers.add_parser("llm", help="inspect the configured language model")
    llm.add_subparsers(dest="llm_command", required=True).add_parser("status")

    stt = subparsers.add_parser("stt", help="inspect speech recognition")
    stt.add_subparsers(dest="stt_command", required=True).add_parser("status")

    transcribe = subparsers.add_parser("transcribe", help="transcribe a WAV file")
    transcribe.add_argument("audio", type=Path)

    listen = subparsers.add_parser("listen", help="capture, transcribe, and answer")
    listen.add_argument(
        "--seconds", type=float,
        help="record a fixed window instead of interactive push-to-talk",
    )
    listen.add_argument("--max-seconds", type=float, default=30.0)
    listen.add_argument("--character")
    listen.add_argument("--actor")
    listen.add_argument("--conversation", default="microphone")
    listen.add_argument("--live", action="store_true", help="play the spoken answer")

    ask = subparsers.add_parser("ask", help="run one interaction")
    ask.add_argument("question")
    ask.add_argument("--character")
    ask.add_argument("--actor")
    ask.add_argument("--conversation", default="cli")
    ask.add_argument(
        "--live", action="store_true",
        help="perform real synthesis and playback (default is hardware-safe)",
    )
    return parser


def _devices_list(inputs: bool = False) -> int:
    devices = list_audio_inputs() if inputs else list_audio_outputs()
    print(json.dumps([
        {
            "selector": item.selector,
            "name": item.name,
            "host_api": item.host_api,
            "output_channels": item.output_channels,
            "input_channels": item.input_channels,
            "default": item.is_default,
        }
        for item in devices
    ], indent=2))
    return 0


def _config_validate(path: Path, live: bool) -> int:
    config = load_config(path)
    errors = (
        live_environment_errors(config) + stt_environment_errors(config)
        if live else []
    )
    if errors:
        print(json.dumps({"valid": False, "config": str(path), "errors": errors}, indent=2))
        return 1
    print(json.dumps({"valid": True, "config": str(path), "live": live}, indent=2))
    return 0


async def _ask(args) -> int:
    return await _perform_question(args, args.question)


async def _perform_question(args, question: str) -> int:
    config = load_config(args.config)
    if args.live:
        errors = live_environment_errors(config)
        if errors:
            raise ConfigurationError("; ".join(errors))
    character_id = args.character or config.default_character
    actor_id = args.actor or config.default_actor
    application = build_application(config, live=args.live)
    try:
        character = application.characters[character_id]
    except KeyError as exc:
        raise ConfigurationError(f"unknown character: {character_id}") from exc
    result = await application.orchestrator.perform(
        Utterance(question, character_id, args.conversation), character, actor_id
    )
    print(json.dumps({
        "mode": "live" if args.live else "safe",
        "character": character_id,
        "actor": result.actor_id,
        "route": result.route_id,
        "source": result.plan.source.value,
        "response": result.plan.text,
        "played": result.played,
        "stall_played": result.stall_played,
        "attempts": [
            {"rule": item.rule, "matched": item.matched, "duration_ms": item.duration_ms}
            for item in result.dispatch_trace.attempts
        ],
        "timings": {
            "dispatch_ms": result.timings.dispatch_ms,
            "synthesis_ms": result.timings.synthesis_ms,
            "queue_wait_ms": result.timings.queue_wait_ms,
            "playback_ms": result.timings.playback_ms,
            "total_ms": result.timings.total_ms,
        },
    }, indent=2))
    return 0


async def _stt_status(path: Path) -> int:
    config = load_config(path)
    provider = build_stt_provider(config)
    errors = provider.status_errors() if isinstance(provider, WhisperCppSTTProvider) else []
    print(json.dumps({
        "provider": config.stt.provider,
        "model": config.stt.model,
        "ready": not errors,
        "errors": errors,
    }, indent=2))
    return 0 if not errors else 1


async def _transcribe(path: Path, audio: Path) -> int:
    if not audio.is_file():
        raise ConfigurationError(f"audio file not found: {audio}")
    config = load_config(path)
    text = await build_stt_provider(config).transcribe(audio)
    print(json.dumps({"provider": config.stt.provider, "transcript": text}, indent=2))
    return 0


async def _listen(args) -> int:
    config = load_config(args.config)
    errors = stt_environment_errors(config)
    if args.live:
        errors.extend(live_environment_errors(config))
    if errors:
        raise ConfigurationError("; ".join(errors))
    recorder = MicrophoneRecorder(
        config.microphone.device,
        config.microphone.sample_rate,
        config.microphone.channels,
    )
    if args.seconds is not None:
        print(f"Listening for {args.seconds:g} seconds...", flush=True)
        audio = await recorder.record(args.seconds)
    else:
        await asyncio.to_thread(input, "Press Enter to start recording...")
        stop = threading.Event()
        recording = asyncio.create_task(recorder.record_until(stop, args.max_seconds))
        await asyncio.sleep(0.15)
        try:
            await asyncio.to_thread(input, "Recording. Press Enter to stop... ")
        finally:
            stop.set()
        audio = await recording
    try:
        transcript = await build_stt_provider(config).transcribe(audio)
    finally:
        audio.unlink(missing_ok=True)
    print(f"Heard: {transcript}", flush=True)
    return await _perform_question(args, transcript)


async def _llm_status(path: Path) -> int:
    config = load_config(path)
    if config.llm.provider != "ollama":
        print(json.dumps({"provider": config.llm.provider, "configured": True}, indent=2))
        return 0
    provider = OllamaLLMProvider(OllamaConfig(config.llm.endpoint, config.llm.model, 3.0))
    models = await provider.list_models()
    available = config.llm.model in models
    print(json.dumps({
        "provider": "ollama",
        "endpoint": config.llm.endpoint,
        "model": config.llm.model,
        "running": True,
        "model_available": available,
        "models": models,
    }, indent=2))
    return 0 if available else 1


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "devices":
            return _devices_list(args.devices_command == "inputs")
        if args.command == "config":
            return _config_validate(args.config, args.live)
        if args.command == "llm":
            return asyncio.run(_llm_status(args.config))
        if args.command == "stt":
            return asyncio.run(_stt_status(args.config))
        if args.command == "transcribe":
            return asyncio.run(_transcribe(args.config, args.audio))
        if args.command == "listen":
            return asyncio.run(_listen(args))
        if args.command == "ask":
            return asyncio.run(_ask(args))
    except (
        ConfigurationError,
        LLMProviderError,
        TranscriptionError,
        LookupError,
        RuntimeError,
    ) as exc:
        print(f"error: {exc}")
        return 2
    return 2
