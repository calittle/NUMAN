"""Microphone capture and interchangeable speech-to-text providers."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .devices import resolve_input_device


class TranscriptionError(RuntimeError):
    pass


class STTProvider(Protocol):
    async def transcribe(self, audio_path: Path) -> str: ...


@dataclass(frozen=True, slots=True)
class WhisperCppConfig:
    model_path: Path
    command: str = "whisper-cli"
    language: str = "en"
    timeout_s: float = 60.0
    prompt: str = ""


class WhisperCppSTTProvider:
    def __init__(self, config: WhisperCppConfig) -> None:
        command = resolve_whisper_command(config.command)
        self._config = WhisperCppConfig(
            model_path=config.model_path,
            command=str(command),
            language=config.language,
            timeout_s=config.timeout_s,
            prompt=config.prompt,
        )

    def status_errors(self) -> list[str]:
        errors = []
        if shutil.which(self._config.command) is None:
            errors.append(f"command not found: {self._config.command}")
        if not self._config.model_path.is_file():
            errors.append(f"model not found: {self._config.model_path}")
        return errors

    async def transcribe(self, audio_path: Path) -> str:
        errors = self.status_errors()
        if errors:
            raise TranscriptionError("; ".join(errors))
        output_stem = Path(tempfile.gettempdir()) / f"numan-stt-{uuid4().hex}"
        output_text = output_stem.with_suffix(".txt")
        argv = [
            self._config.command,
            "-m", str(self._config.model_path),
            "-f", str(audio_path),
            "-l", self._config.language,
            "--no-gpu",
            "--no-timestamps",
            "--output-txt",
            "--output-file", str(output_stem),
        ]
        if self._config.prompt:
            argv.extend(["--prompt", self._config.prompt])
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self._config.timeout_s
                )
            except asyncio.TimeoutError as exc:
                process.terminate()
                await process.wait()
                raise TranscriptionError("local transcription timed out") from exc
            if process.returncode:
                detail = stderr.decode(errors="replace").strip()[-500:]
                raise TranscriptionError(f"whisper.cpp failed: {detail}")
            text = output_text.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise TranscriptionError(f"cannot run whisper.cpp: {exc}") from exc
        finally:
            output_text.unlink(missing_ok=True)
        if not text:
            raise TranscriptionError("no speech was recognized")
        return text


@dataclass(frozen=True, slots=True)
class WhisperServerConfig:
    model_path: Path
    command: str = "whisper-server"
    language: str = "en"
    prompt: str = ""
    host: str = "127.0.0.1"
    port: int = 8178
    use_gpu: bool = False
    startup_timeout_s: float = 20.0
    request_timeout_s: float = 60.0


class WhisperServerSTTProvider:
    """Long-lived whisper.cpp server that loads its model once."""

    def __init__(self, config: WhisperServerConfig) -> None:
        command = resolve_whisper_command(config.command)
        self._config = WhisperServerConfig(
            model_path=config.model_path,
            command=str(command),
            language=config.language,
            prompt=config.prompt,
            host=config.host,
            port=config.port,
            use_gpu=config.use_gpu,
            startup_timeout_s=config.startup_timeout_s,
            request_timeout_s=config.request_timeout_s,
        )
        self._process: asyncio.subprocess.Process | None = None
        self._start_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()

    def status_errors(self) -> list[str]:
        errors = []
        if shutil.which(self._config.command) is None and not Path(self._config.command).is_file():
            errors.append(f"command not found: {self._config.command}")
        if not self._config.model_path.is_file():
            errors.append(f"model not found: {self._config.model_path}")
        return errors

    async def start(self) -> None:
        async with self._start_lock:
            if self._process is not None and self._process.returncode is None:
                return
            errors = self.status_errors()
            if errors:
                raise TranscriptionError("; ".join(errors))
            argv = [
                self._config.command,
                "-m", str(self._config.model_path),
                "--host", self._config.host,
                "--port", str(self._config.port),
                "-l", self._config.language,
                "--no-timestamps",
            ]
            if self._config.prompt:
                argv.extend(["--prompt", self._config.prompt])
            if not self._config.use_gpu:
                argv.append("--no-gpu")
            self._process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            deadline = asyncio.get_running_loop().time() + self._config.startup_timeout_s
            while asyncio.get_running_loop().time() < deadline:
                if self._process.returncode is not None:
                    detail = (await self._process.stderr.read()).decode(errors="replace")[-500:]
                    raise TranscriptionError(f"whisper-server failed to start: {detail.strip()}")
                try:
                    reader, writer = await asyncio.open_connection(
                        self._config.host, self._config.port
                    )
                    writer.close()
                    await writer.wait_closed()
                    return
                except OSError:
                    await asyncio.sleep(0.05)
            await self.close()
            raise TranscriptionError("whisper-server did not become ready in time")

    async def transcribe(self, audio_path: Path) -> str:
        await self.start()
        async with self._request_lock:
            return await asyncio.to_thread(self._transcribe_sync, audio_path)

    def _transcribe_sync(self, audio_path: Path) -> str:
        boundary = f"numan-{uuid4().hex}"
        audio = audio_path.read_bytes()
        body = _multipart_body(boundary, audio_path.name, audio)
        request = urllib.request.Request(
            f"http://{self._config.host}:{self._config.port}/inference",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._config.request_timeout_s
            ) as response:
                payload = json.load(response)
            text = payload["text"].strip()
        except (OSError, urllib.error.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise TranscriptionError(f"local transcription failed: {exc}") from exc
        if not text:
            raise TranscriptionError("no speech was recognized")
        return text

    async def close(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


def _multipart_body(boundary: str, filename: str, audio: bytes) -> bytes:
    marker = boundary.encode("ascii")
    return b"".join((
        b"--" + marker + b"\r\n",
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: audio/wav\r\n\r\n",
        audio,
        b"\r\n--" + marker + b"\r\n",
        b'Content-Disposition: form-data; name="response_format"\r\n\r\n',
        b"json\r\n",
        b"--" + marker + b"--\r\n",
    ))


def resolve_whisper_command(command: str) -> Path:
    """Find whisper.cpp from PATH, the venv, or NUMAN's portable tools folder."""
    found = shutil.which(command)
    if found:
        return Path(found)
    suffix = ".exe" if sys.platform == "win32" else ""
    name = Path(command).name
    if suffix and not name.casefold().endswith(suffix):
        name += suffix
    candidates = (
        Path(sys.executable).parent / name,
        Path(__file__).resolve().parents[2] / "tools" / "whisper" / name,
    )
    return next((path for path in candidates if path.is_file()), Path(command))


@dataclass(frozen=True, slots=True)
class DeepgramConfig:
    endpoint: str
    api_key_env: str = "DEEPGRAM_API_KEY"
    timeout_s: float = 30.0


class DeepgramSTTProvider:
    def __init__(self, config: DeepgramConfig) -> None:
        self._config = config

    async def transcribe(self, audio_path: Path) -> str:
        return await asyncio.to_thread(self._transcribe_sync, audio_path)

    def _transcribe_sync(self, audio_path: Path) -> str:
        key = os.environ.get(self._config.api_key_env, "").strip()
        if not key:
            raise TranscriptionError(
                f"missing API key environment variable: {self._config.api_key_env}"
            )
        request = urllib.request.Request(
            self._config.endpoint,
            data=audio_path.read_bytes(),
            headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._config.timeout_s) as response:
                payload = json.load(response)
            text = payload["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
        except (OSError, urllib.error.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise TranscriptionError(f"Deepgram transcription failed: {exc}") from exc
        if not text:
            raise TranscriptionError("no speech was recognized")
        return text


class MicrophoneRecorder:
    """The sole owner of one microphone stream during a capture window."""

    def __init__(self, device: str, sample_rate: int = 16_000, channels: int = 1):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self._lock = asyncio.Lock()

    async def record(self, duration_s: float) -> Path:
        if duration_s <= 0:
            raise ValueError("recording duration must be positive")
        async with self._lock:
            return await asyncio.to_thread(self._record_sync, duration_s)

    async def record_until(
        self, stop: threading.Event, max_duration_s: float = 30.0
    ) -> Path:
        if max_duration_s <= 0:
            raise ValueError("maximum recording duration must be positive")
        async with self._lock:
            return await asyncio.to_thread(
                self._record_until_sync, stop, max_duration_s
            )

    def _record_sync(self, duration_s: float) -> Path:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise TranscriptionError("sounddevice is required for microphone capture") from exc
        try:
            device_index = resolve_input_device(self.device)
            frames = sd.rec(
                int(duration_s * self.sample_rate),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=device_index,
            )
            sd.wait()
        except Exception as exc:
            raise TranscriptionError(f"microphone capture failed: {exc}") from exc
        return self._write_wav(frames.tobytes())

    def _record_until_sync(
        self, stop: threading.Event, max_duration_s: float
    ) -> Path:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise TranscriptionError("sounddevice is required for microphone capture") from exc
        chunks: list[bytes] = []

        def callback(indata, frames, time_info, status):
            del frames, time_info, status
            chunks.append(bytes(indata))

        try:
            device_index = resolve_input_device(self.device)
            started = time.monotonic()
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=device_index,
                callback=callback,
                blocksize=1024,
            ):
                while not stop.wait(0.05):
                    if time.monotonic() - started >= max_duration_s:
                        break
        except Exception as exc:
            raise TranscriptionError(f"microphone capture failed: {exc}") from exc
        if not chunks:
            raise TranscriptionError("microphone captured no audio")
        return self._write_wav(b"".join(chunks))

    def _write_wav(self, frames: bytes) -> Path:
        output = Path(tempfile.gettempdir()) / f"numan-mic-{uuid4().hex}.wav"
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(frames)
        return output
