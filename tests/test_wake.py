import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from numan.application import PROJECT_ROOT, build_wake_registry
from numan.configuration import ConfigurationError, load_config
from numan.wake import (
    SpeechCapture,
    SherpaKeywordDetector,
    SherpaWakeConfig,
    WakeError,
    WakeRegistry,
    WakeTarget,
    normalize_phrase,
    sherpa_cli_path,
)
from numan.wake import WakeListener


class WakeRegistryTests(unittest.TestCase):
    def test_finds_windows_compiler_next_to_python(self):
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / "python.exe"
            command = Path(directory) / "sherpa-onnx-cli.exe"
            command.touch()
            with patch("numan.wake.sys.platform", "win32"), patch(
                "numan.wake.sys.executable", str(python)
            ):
                self.assertEqual(sherpa_cli_path(), command)

    def test_resolves_phrase_to_character_and_actor(self):
        grog = WakeTarget("grog", ("Hey Captain Grog",), "grog", "bird-one")
        captain = WakeTarget("captain", ("Hey Captain", "Captain"), "captain", "bird-two")
        registry = WakeRegistry((grog, captain))
        self.assertEqual(registry.resolve("  HEY   captain "), captain)
        self.assertEqual(normalize_phrase(" Hey  Captain Grog "), "hey captain grog")

    def test_unknown_detection_is_rejected(self):
        registry = WakeRegistry((WakeTarget("n", ("hey n",), "n", "bird"),))
        with self.assertRaises(WakeError):
            registry.resolve("hey somebody")

    def test_duplicate_phrase_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            WakeRegistry((
                WakeTarget("one", ("Hey Bird",), "one", "a"),
                WakeTarget("two", ("hey  bird",), "two", "b"),
            ))

    def test_listener_routes_detection_and_stops_cleanly(self):
        target = WakeTarget("grog", ("hey captain grog",), "grog", "bird")
        registry = WakeRegistry((target,))

        class Detector:
            def __init__(self):
                self.calls = 0

            def process(self, frame):
                self.calls += 1
                return "hey captain grog" if self.calls == 1 else None

            def reset(self):
                pass

        class Stream:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]

            def __enter__(self):
                samples = np.zeros(512 * 8, dtype=np.int16).tobytes()
                self.callback(samples, 512 * 8, None, None)
                return self

            def __exit__(self, *args):
                return None

        listener = WakeListener(Detector(), registry)
        detected = []
        worker = threading.Thread(target=listener.run, args=(detected.append,))
        with patch.dict("sys.modules", {"sounddevice": type("SD", (), {"RawInputStream": Stream})}):
            worker.start()
            time.sleep(0.1)
            listener.stop()
            worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(detected, [target])

    def test_listener_retains_configured_end_silence(self):
        registry = WakeRegistry((
            WakeTarget("grog", ("hey captain grog",), "grog", "bird"),
        ))
        listener = WakeListener(object(), registry, end_silence_s=0.6)
        self.assertEqual(listener.end_silence_s, 0.6)


class SherpaKeywordDetectorTests(unittest.TestCase):
    def test_detection_returns_keyword_and_starts_a_fresh_stream(self):
        class Stream:
            def __init__(self):
                self.decoded = False

            def accept_waveform(self, sample_rate, samples):
                self.sample_rate = sample_rate
                self.samples = samples

        class Spotter:
            def __init__(self, **kwargs):
                self.streams = []

            def create_stream(self):
                stream = Stream()
                self.streams.append(stream)
                return stream

            def is_ready(self, stream):
                return not stream.decoded

            def decode_stream(self, stream):
                stream.decoded = True

            def get_result(self, stream):
                return types.SimpleNamespace(keyword="hey captain grog")

        module = types.SimpleNamespace(KeywordSpotter=Spotter)
        config = SherpaWakeConfig(Path("models"))
        with patch.dict("sys.modules", {"sherpa_onnx": module}):
            detector = SherpaKeywordDetector(config, Path("keywords.txt"))
        original_stream = detector._stream

        self.assertEqual(
            detector.process(np.zeros(512, dtype=np.int16)),
            "hey captain grog",
        )
        self.assertIsNot(detector._stream, original_stream)


class SpeechCaptureTests(unittest.TestCase):
    def test_waits_for_speech_and_completes_after_silence(self):
        capture = SpeechCapture(
            speech_threshold=100,
            start_timeout_s=1,
            end_silence_s=0.064,
            pre_roll_s=0.032,
        )
        silence = np.zeros(512, dtype=np.int16).tobytes()
        speech = np.full(512, 1000, dtype=np.int16).tobytes()
        self.assertIsNone(capture.feed(silence))
        self.assertIsNone(capture.feed(speech))
        self.assertIsNone(capture.feed(speech))
        self.assertIsNone(capture.feed(silence))
        result = capture.feed(silence)
        self.assertIsNotNone(result)
        self.assertGreater(len(result), len(speech) * 2)

    def test_default_capture_accepts_quiet_speech_above_background(self):
        capture = SpeechCapture(end_silence_s=0.064)
        background = np.full(512, 8, dtype=np.int16).tobytes()
        quiet_speech = np.full(512, 225, dtype=np.int16).tobytes()
        self.assertIsNone(capture.feed(background))
        self.assertFalse(capture.speech_started)
        self.assertIsNone(capture.feed(quiet_speech))
        self.assertTrue(capture.speech_started)
        self.assertIsNone(capture.feed(background))
        self.assertIsNotNone(capture.feed(background))

    def test_steady_room_noise_is_learned_as_silence(self):
        capture = SpeechCapture(
            initial_noise_floor=300,
            end_silence_s=0.064,
            retained_silence_s=0.032,
        )
        room_noise = np.full(512, 300, dtype=np.int16).tobytes()
        speech = np.full(512, 1000, dtype=np.int16).tobytes()
        self.assertIsNone(capture.feed(room_noise))
        self.assertFalse(capture.speech_started)
        self.assertIsNone(capture.feed(speech))
        self.assertTrue(capture.speech_started)
        self.assertIsNone(capture.feed(room_noise))
        result = capture.feed(room_noise)
        self.assertIsNotNone(result)
        self.assertEqual(capture.trailing_silence_ms, 64.0)

    def test_expires_when_no_question_follows_wake(self):
        capture = SpeechCapture(start_timeout_s=0.064)
        silence = np.zeros(512, dtype=np.int16).tobytes()
        capture.feed(silence)
        capture.feed(silence)
        self.assertTrue(capture.expired)


class WakeConfigurationTests(unittest.TestCase):
    def test_checked_in_target_builds(self):
        config = load_config(PROJECT_ROOT / "config/numan.toml")
        registry = build_wake_registry(config)
        grog = registry.resolve("hey captain grog")
        polly = registry.resolve("hey polly")
        self.assertEqual((grog.character_id, grog.actor_id), ("grog", "grog-dev"))
        self.assertEqual((polly.character_id, polly.actor_id), ("polly", "polly-dev"))

    def test_duplicate_configured_phrase_fails_validation(self):
        source = (PROJECT_ROOT / "config/numan.toml").read_text(encoding="utf-8")
        source += """

[wake.targets.other]
phrases = ["HEY CAPTAIN GROG"]
character = "grog"
actor = "grog-dev"
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.toml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "duplicate wake phrase"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
