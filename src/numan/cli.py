"""NUMAN command line interface."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import shutil
import sys
import threading
from pathlib import Path

from .application import (
    PROJECT_ROOT,
    build_application,
    build_stt_provider,
    build_wake_config,
    build_wake_registry,
    live_environment_errors,
    resolve_actor_id,
    stt_environment_errors,
)
from .configuration import ConfigurationError, load_config
from .devices import list_audio_inputs, list_audio_outputs, resolve_input_device
from .engine.models import Utterance
from .engine.providers import LLMProviderError, OllamaConfig, OllamaLLMProvider
from .transcription import MicrophoneRecorder, TranscriptionError, WhisperCppSTTProvider
from .wake import (
    SherpaKeywordCompiler,
    SherpaKeywordDetector,
    WakeError,
    WakeListener,
)

DEFAULT_CONFIG = PROJECT_ROOT / "config/numan.toml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="numan")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="check whether NUMAN is ready to run")

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

    show = subparsers.add_parser("show", help="inspect semantic show control")
    show.add_subparsers(dest="show_command", required=True).add_parser("status")

    wake = subparsers.add_parser("wake", help="configure and test wake words")
    wake_commands = wake.add_subparsers(dest="wake_command", required=True)
    wake_commands.add_parser("status")
    wake_commands.add_parser("compile")
    wake_commands.add_parser("listen", help="print routed wake detections")
    wake_run = wake_commands.add_parser("run", help="wake, capture, transcribe, and answer")
    wake_run.add_argument("--live", action="store_true", help="play spoken answers")

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
    actor_id = resolve_actor_id(config, character_id, args.actor)
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
        "show_actions": list(result.plan.show_actions),
        "scheduled_actions": [
            {
                "id": item.id,
                "action": item.action.name,
                "delay_seconds": item.delay_seconds,
                "status": item.status,
                "due_at": item.due_at.isoformat(),
            }
            for item in result.scheduled_actions
        ],
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


def _show_status(path: Path) -> int:
    config = load_config(path)
    print(json.dumps({
        "provider": config.show_control.provider,
        "hardware_safe": config.show_control.provider in {"fake", "none"},
        "allowed_actions": sorted(config.show_control.allowed_actions),
        "destination": (
            {"host": config.show_control.host, "port": config.show_control.port}
            if config.show_control.provider == "lor-osc-trigger" else None
        ),
        "triggers": {
            action: {
                "network": item.network,
                "unit": item.unit,
                "circuit": item.circuit,
            }
            for action, item in config.show_control.triggers.items()
        },
        "characters": {
            item.id: sorted(item.show_actions)
            for item in config.characters.values()
        },
    }, indent=2))
    return 0


async def _transcribe(path: Path, audio: Path) -> int:
    if not audio.is_file():
        raise ConfigurationError(f"audio file not found: {audio}")
    config = load_config(path)
    text = await build_stt_provider(config).transcribe(audio)
    print(json.dumps({"provider": config.stt.provider, "transcript": text}, indent=2))
    return 0


async def _wake(args) -> int:
    path = args.config
    command = args.wake_command
    config = load_config(path)
    wake_config = build_wake_config(config)
    registry = build_wake_registry(config)
    errors = SherpaKeywordDetector.status_errors(wake_config)
    if command == "status":
        print(json.dumps({
            "enabled": config.wake.enabled,
            "ready": not errors,
            "model_dir": str(wake_config.model_dir),
            "targets": [
                {
                    "id": target.id,
                    "phrases": target.phrases,
                    "character": target.character_id,
                    "actor": target.actor_id,
                }
                for target in registry.targets
            ],
            "errors": errors,
        }, indent=2))
        return 0 if not errors else 1
    if errors:
        raise ConfigurationError("; ".join(errors))
    keywords = await SherpaKeywordCompiler().compile(
        wake_config.model_dir, registry.phrases
    )
    if command == "compile":
        print(json.dumps({
            "compiled": True,
            "keywords_file": str(keywords),
            "phrases": registry.phrases,
        }, indent=2))
        return 0
    detector = SherpaKeywordDetector(wake_config, keywords)
    microphone = resolve_input_device(config.microphone.device)
    listener = WakeListener(detector, registry, microphone)
    print("Listening for: " + ", ".join(registry.phrases), flush=True)
    print("Press Ctrl-C to stop.", flush=True)
    on_query = None
    if command == "run":
        errors = stt_environment_errors(config)
        if args.live:
            errors.extend(live_environment_errors(config))
        if errors:
            raise ConfigurationError("; ".join(errors))
        application = build_application(config, live=args.live)
        stt_provider = build_stt_provider(config)
        loop = asyncio.get_running_loop()

        async def answer(target, audio):
            character = application.characters[target.character_id]
            transcript = ""

            def report_transcript(text):
                nonlocal transcript
                transcript = text
                print(f"Heard ({target.id}): {text}", flush=True)

            result = await application.orchestrator.perform_audio(
                audio, stt_provider.transcribe, character, target.actor_id,
                f"wake-{target.id}", on_transcript=report_transcript,
            )
            print(json.dumps({
                "wake_target": target.id,
                "transcript": transcript,
                "character": target.character_id,
                "actor": target.actor_id,
                "source": result.plan.source.value,
                "response": result.plan.text,
                "played": result.played,
                "stall_played": result.stall_played,
                "show_actions": list(result.plan.show_actions),
                "scheduled_actions": [
                    {
                        "id": item.id,
                        "action": item.action.name,
                        "delay_seconds": item.delay_seconds,
                        "status": item.status,
                        "due_at": item.due_at.isoformat(),
                    }
                    for item in result.scheduled_actions
                ],
            }, indent=2), flush=True)

        def submit_query(target, audio):
            asyncio.run_coroutine_threadsafe(answer(target, audio), loop).result()

        on_query = submit_query
    try:
        await asyncio.to_thread(
            listener.run,
            lambda target: print(
                f"WAKE {target.id}: character={target.character_id} actor={target.actor_id}",
                flush=True,
            ),
            on_query=on_query,
        )
    except asyncio.CancelledError:
        listener.stop()
        print("\nWake listener stopped.", flush=True)
        return 130
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


async def _doctor(path: Path) -> int:
    """Plain-language readiness report intended for the installation owner."""
    config = load_config(path)
    checks: list[tuple[str, bool, str]] = []
    setup_hint = (
        "double-click scripts\\windows\\SETUP-NUMAN.cmd"
        if sys.platform == "win32"
        else "install FFmpeg with your system package manager"
    )

    checks.append((
        "Python",
        sys.version_info >= (3, 12),
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    ))
    checks.append((
        "FFmpeg",
        shutil.which("ffmpeg") is not None,
        "ready" if shutil.which("ffmpeg") else f"not found; {setup_hint}",
    ))
    checks.append((
        "Voice software",
        importlib.util.find_spec("edge_tts") is not None,
        "ready" if importlib.util.find_spec("edge_tts") else "not installed; rerun setup",
    ))

    stt_errors = stt_environment_errors(config)
    checks.append((
        "Speech recognition",
        not stt_errors,
        "ready" if not stt_errors else "; ".join(stt_errors),
    ))
    wake_errors = SherpaKeywordDetector.status_errors(build_wake_config(config))
    checks.append((
        "Wake words",
        not wake_errors,
        "ready" if not wake_errors else "; ".join(wake_errors),
    ))

    try:
        inputs = list_audio_inputs()
        outputs = list_audio_outputs()
        audio_detail = f"{len(inputs)} input(s), {len(outputs)} output(s) found"
        audio_ok = bool(inputs and outputs)
    except Exception as exc:
        audio_ok = False
        audio_detail = f"audio check failed: {exc}"
    checks.append(("Audio devices", audio_ok, audio_detail))

    if config.llm.provider == "ollama":
        try:
            provider = OllamaLLMProvider(
                OllamaConfig(config.llm.endpoint, config.llm.model, 3.0)
            )
            models = await provider.list_models()
            llm_ok = config.llm.model in models
            llm_detail = (
                f"{config.llm.model} is ready"
                if llm_ok else f"run: ollama pull {config.llm.model}"
            )
        except Exception as exc:
            llm_ok = False
            llm_detail = f"Ollama is not responding: {exc}"
    else:
        llm_ok = True
        llm_detail = f"configured provider: {config.llm.provider}"
    checks.append(("Local brain", llm_ok, llm_detail))

    print("NUMAN readiness check\n")
    for name, ok, detail in checks:
        print(f"[{'OK' if ok else 'FIX'}] {name}: {detail}")
    problems = sum(not ok for _, ok, _ in checks)
    if problems:
        print(f"\n{problems} item(s) need attention. See docs/ROB-GUIDE.md.")
        return 1
    print("\nEverything needed for normal operation is ready.")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "devices":
            return _devices_list(args.devices_command == "inputs")
        if args.command == "doctor":
            return asyncio.run(_doctor(args.config))
        if args.command == "config":
            return _config_validate(args.config, args.live)
        if args.command == "llm":
            return asyncio.run(_llm_status(args.config))
        if args.command == "stt":
            return asyncio.run(_stt_status(args.config))
        if args.command == "show":
            return _show_status(args.config)
        if args.command == "wake":
            return asyncio.run(_wake(args))
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
        WakeError,
    ) as exc:
        print(f"error: {exc}")
        return 2
    return 2
