import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from numan.model_assets import (
    VoiceModelAsset,
    install_voice_models,
    verify_voice_models,
)


class VoiceModelAssetTests(unittest.TestCase):
    def test_install_is_atomic_and_checksum_verified(self):
        content = b"offline voice model"
        asset = VoiceModelAsset(
            "piper", "models/test.onnx", "https://example.invalid/test",
            hashlib.sha256(content).hexdigest(),
        )

        with tempfile.TemporaryDirectory() as directory:
            progress = []
            with patch("numan.model_assets.VOICE_MODEL_ASSETS", (asset,)):
                installed = install_voice_models(
                    directory,
                    "piper",
                    opener=lambda _: io.BytesIO(content),
                    progress=lambda model, phase, current, total: progress.append(
                        (model, phase, current, total)
                    ),
                )
                results = verify_voice_models(directory, "piper")

            self.assertEqual(installed, [Path(directory) / "models/test.onnx"])
            self.assertTrue(results[0]["valid"])
            self.assertEqual(list(Path(directory).rglob("*.partial")), [])
            self.assertEqual(
                [event[1] for event in progress],
                ["checking", "downloading", "downloading", "verifying", "installed"],
            )

    def test_bad_checksum_is_not_published(self):
        asset = VoiceModelAsset(
            "kokoro", "models/test.onnx", "https://example.invalid/test", "0" * 64
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch("numan.model_assets.VOICE_MODEL_ASSETS", (asset,)):
                with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                    install_voice_models(
                        directory, "kokoro", opener=lambda _: io.BytesIO(b"bad")
                    )
            self.assertFalse((Path(directory) / "models/test.onnx").exists())


if __name__ == "__main__":
    unittest.main()
