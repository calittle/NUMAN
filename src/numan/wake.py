"""Configurable, multi-target keyword spotting over one microphone stream."""

from __future__ import annotations

import asyncio
import queue
import shutil
import sys
import tempfile
import threading
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path


class WakeError(RuntimeError):
    pass


def normalize_phrase(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass(frozen=True, slots=True)
class WakeTarget:
    id: str
    phrases: tuple[str, ...]
    character_id: str
    actor_id: str


class WakeRegistry:
    def __init__(self, targets: tuple[WakeTarget, ...]) -> None:
        self.targets = targets
        self._phrases: dict[str, WakeTarget] = {}
        for target in targets:
            for phrase in target.phrases:
                key = normalize_phrase(phrase)
                if key in self._phrases:
                    raise ValueError(f"duplicate wake phrase: {phrase}")
                self._phrases[key] = target

    @property
    def phrases(self) -> tuple[str, ...]:
        return tuple(self._phrases)

    def resolve(self, detected: str) -> WakeTarget:
        key = normalize_phrase(detected)
        try:
            return self._phrases[key]
        except KeyError as exc:
            raise WakeError(f"detector returned unknown phrase: {detected!r}") from exc


@dataclass(frozen=True, slots=True)
class SherpaWakeConfig:
    model_dir: Path
    threshold: float = 0.20
    score: float = 1.0
    sample_rate: int = 16_000


def sherpa_cli_path() -> Path:
    name = "sherpa-onnx-cli.exe" if sys.platform == "win32" else "sherpa-onnx-cli"
    adjacent = Path(sys.executable).parent / name
    return adjacent if adjacent.is_file() else Path("sherpa-onnx-cli")


def model_file(model_dir: Path, component: str) -> Path:
    matches = sorted(model_dir.glob(f"{component}*.onnx"))
    full_precision = [path for path in matches if ".int8." not in path.name]
    selected = full_precision or matches
    if not selected:
        return model_dir / f"{component}.onnx"
    return selected[0]


class SherpaKeywordCompiler:
    def __init__(self, command: str | Path | None = None) -> None:
        self.command = str(command or sherpa_cli_path())

    async def compile(self, model_dir: Path, phrases: tuple[str, ...]) -> Path:
        if not phrases:
            raise WakeError("cannot compile an empty wake phrase list")
        raw = Path(tempfile.gettempdir()) / "numan-wake-keywords-raw.txt"
        output = model_dir / "numan-keywords.txt"
        raw.write_text("\n".join(phrase.upper() for phrase in phrases) + "\n")
        try:
            process = await asyncio.create_subprocess_exec(
                self.command,
                "text2token",
                "--tokens", str(model_dir / "tokens.txt"),
                "--tokens-type", "bpe",
                "--bpe-model", str(model_dir / "bpe.model"),
                str(raw),
                str(output),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        except OSError as exc:
            raise WakeError(f"cannot run keyword compiler: {exc}") from exc
        finally:
            raw.unlink(missing_ok=True)
        if process.returncode or not output.is_file():
            detail = (stderr or stdout).decode(errors="replace").strip()[-500:]
            raise WakeError(f"keyword compilation failed: {detail}")
        return output


class SherpaKeywordDetector:
    REQUIRED_FILES = ("tokens.txt", "bpe.model")

    def __init__(self, config: SherpaWakeConfig, keywords_file: Path) -> None:
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise WakeError("sherpa-onnx is not installed") from exc
        self._sample_rate = config.sample_rate
        self._spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(config.model_dir / "tokens.txt"),
            encoder=str(model_file(config.model_dir, "encoder")),
            decoder=str(model_file(config.model_dir, "decoder")),
            joiner=str(model_file(config.model_dir, "joiner")),
            keywords_file=str(keywords_file),
            keywords_score=config.score,
            keywords_threshold=config.threshold,
            num_trailing_blanks=1,
            provider="cpu",
            num_threads=1,
        )
        self._stream = self._spotter.create_stream()

    @classmethod
    def status_errors(cls, config: SherpaWakeConfig) -> list[str]:
        errors = []
        try:
            import sherpa_onnx  # noqa: F401
        except ImportError:
            errors.append("sherpa-onnx is not installed (install with: pip install -e '.[wake]')")
        cli = sherpa_cli_path()
        if not cli.is_file() and shutil.which(str(cli)) is None:
            errors.append("command not found: sherpa-onnx-cli")
        for component in ("encoder", "decoder", "joiner"):
            path = model_file(config.model_dir, component)
            if not path.is_file():
                errors.append(f"wake model file not found: {path}")
        for name in cls.REQUIRED_FILES:
            if not (config.model_dir / name).is_file():
                errors.append(f"wake model file not found: {config.model_dir / name}")
        return errors

    def process(self, pcm_int16) -> str | None:
        import numpy as np

        self._stream.accept_waveform(
            self._sample_rate, pcm_int16.astype(np.float32) / 32768.0
        )
        while self._spotter.is_ready(self._stream):
            self._spotter.decode_stream(self._stream)
            result = self._spotter.get_result(self._stream)
            keyword = getattr(result, "keyword", result)
            if keyword:
                self._spotter.reset_stream(self._stream)
                return str(keyword)
        return None

    def reset(self) -> None:
        self._spotter.reset_stream(self._stream)


class SpeechCapture:
    """Energy-gated query capture fed by the already-open wake stream."""

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        frame_samples: int = 512,
        speech_threshold: float = 450.0,
        start_timeout_s: float = 5.0,
        end_silence_s: float = 1.1,
        max_duration_s: float = 15.0,
        pre_roll_s: float = 0.25,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self.speech_threshold = speech_threshold
        self.start_limit = int(start_timeout_s * sample_rate / frame_samples)
        self.silence_limit = int(end_silence_s * sample_rate / frame_samples)
        self.max_frames = int(max_duration_s * sample_rate / frame_samples)
        self.pre_roll = deque(maxlen=max(1, int(pre_roll_s * sample_rate / frame_samples)))
        self.frames: list[bytes] = []
        self.total_frames = 0
        self.silence_frames = 0
        self.speech_started = False
        self.expired = False

    def feed(self, frame: bytes) -> bytes | None:
        import numpy as np

        self.total_frames += 1
        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0
        speaking = rms >= self.speech_threshold
        if not self.speech_started:
            self.pre_roll.append(frame)
            if speaking:
                self.speech_started = True
                self.frames.extend(self.pre_roll)
                self.pre_roll.clear()
            elif self.total_frames >= self.start_limit:
                self.expired = True
            return None

        self.frames.append(frame)
        self.silence_frames = 0 if speaking else self.silence_frames + 1
        if self.silence_frames >= self.silence_limit or self.total_frames >= self.max_frames:
            return b"".join(self.frames)
        return None


def write_capture_wav(pcm: bytes, sample_rate: int = 16_000) -> Path:
    output = Path(tempfile.gettempdir()) / f"numan-wake-{threading.get_ident()}.wav"
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return output


class WakeListener:
    """One continuous input stream feeding all configured wake targets."""

    def __init__(
        self,
        detector,
        registry: WakeRegistry,
        microphone_device=None,
    ):
        self.detector = detector
        self.registry = registry
        self.microphone_device = microphone_device
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(
        self,
        on_wake,
        *,
        on_query=None,
        running=None,
        suppressed=lambda: False,
    ) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise WakeError("wake listening requires numpy and sounddevice") from exc
        chunks: queue.Queue[bytes] = queue.Queue(maxsize=50)

        def callback(indata, frames, time_info, status):
            del frames, time_info, status
            data = bytes(indata)
            if chunks.full():
                try:
                    chunks.get_nowait()
                except queue.Empty:
                    pass
            chunks.put_nowait(data)

        pending = bytearray()
        frame_bytes = 512 * 2
        keep_running = running or (lambda: not self._stop.is_set())
        capture: SpeechCapture | None = None
        active_target: WakeTarget | None = None
        with sd.RawInputStream(
            samplerate=16_000,
            channels=1,
            dtype="int16",
            device=self.microphone_device,
            callback=callback,
            blocksize=512,
        ):
            while keep_running() and not self._stop.is_set():
                try:
                    pending.extend(chunks.get(timeout=0.5))
                except queue.Empty:
                    continue
                while len(pending) >= frame_bytes:
                    frame = bytes(pending[:frame_bytes])
                    del pending[:frame_bytes]
                    if capture is not None:
                        pcm = capture.feed(frame)
                        if pcm is not None:
                            audio = write_capture_wav(pcm)
                            try:
                                if on_query is not None:
                                    on_query(active_target, audio)
                            finally:
                                audio.unlink(missing_ok=True)
                            capture = None
                            active_target = None
                            self.detector.reset()
                            pending.clear()
                            while True:
                                try:
                                    chunks.get_nowait()
                                except queue.Empty:
                                    break
                        elif capture.expired:
                            capture = None
                            active_target = None
                            self.detector.reset()
                        continue
                    detected = self.detector.process(np.frombuffer(frame, dtype=np.int16))
                    if detected and not suppressed():
                        active_target = self.registry.resolve(detected)
                        on_wake(active_target)
                        if on_query is not None:
                            capture = SpeechCapture()
                        pending.clear()
                        break
