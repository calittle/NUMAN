import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from numan.application import PROJECT_ROOT, build_wake_registry
from numan.configuration import ConfigurationError, load_config
from numan.wake import (
    SpeechCapture,
    WakeError,
    WakeRegistry,
    WakeTarget,
    normalize_phrase,
)
from numan.wake import WakeListener


class WakeRegistryTests(unittest.TestCase):
    def test_resolves_phrase_to_character_and_actor(self):
        nigel = WakeTarget("nigel", ("Hey Nigel",), "nigel", "bird-one")
        captain = WakeTarget("captain", ("Hey Captain", "Captain"), "captain", "bird-two")
        registry = WakeRegistry((nigel, captain))
        self.assertEqual(registry.resolve("  HEY   captain "), captain)
        self.assertEqual(normalize_phrase(" Hey  Nigel "), "hey nigel")

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
        target = WakeTarget("nigel", ("hey nigel",), "nigel", "bird")
        registry = WakeRegistry((target,))

        class Detector:
            def __init__(self):
                self.calls = 0

            def process(self, frame):
                self.calls += 1
                return "hey nigel" if self.calls == 1 else None

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

    def test_expires_when_no_question_follows_wake(self):
        capture = SpeechCapture(start_timeout_s=0.064)
        silence = np.zeros(512, dtype=np.int16).tobytes()
        capture.feed(silence)
        capture.feed(silence)
        self.assertTrue(capture.expired)


class WakeConfigurationTests(unittest.TestCase):
    def test_checked_in_target_builds(self):
        config = load_config(PROJECT_ROOT / "config/numan.toml")
        target = build_wake_registry(config).resolve("hey nigel")
        self.assertEqual((target.character_id, target.actor_id), ("nigel", "nigel-dev"))

    def test_duplicate_configured_phrase_fails_validation(self):
        source = (PROJECT_ROOT / "config/numan.toml").read_text(encoding="utf-8")
        source += """

[wake.targets.other]
phrases = ["HEY NIGEL"]
character = "nigel"
actor = "nigel-dev"
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.toml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "duplicate wake phrase"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
