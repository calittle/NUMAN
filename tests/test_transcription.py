import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from numan.transcription import (
    DeepgramConfig,
    DeepgramSTTProvider,
    TranscriptionError,
    WhisperCppConfig,
    WhisperCppSTTProvider,
)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class DeepgramProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_transcribes_wav_and_uses_token_auth(self):
        payload = {
            "results": {"channels": [{"alternatives": [{"transcript": "Hello Nigel"}]}]}
        }
        captured = {}

        def urlopen(request, timeout):
            captured["authorization"] = request.headers["Authorization"]
            captured["content_type"] = request.headers["Content-type"]
            captured["body"] = request.data
            return _Response(json.dumps(payload).encode())

        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "speech.wav"
            audio.write_bytes(b"RIFF-test")
            provider = DeepgramSTTProvider(
                DeepgramConfig("https://api.deepgram.com/v1/listen", "DG_KEY")
            )
            with patch.dict(os.environ, {"DG_KEY": "secret"}), patch(
                "urllib.request.urlopen", side_effect=urlopen
            ):
                text = await provider.transcribe(audio)

        self.assertEqual(text, "Hello Nigel")
        self.assertEqual(captured["authorization"], "Token secret")
        self.assertEqual(captured["content_type"], "audio/wav")
        self.assertEqual(captured["body"], b"RIFF-test")

    async def test_missing_key_is_clear(self):
        provider = DeepgramSTTProvider(
            DeepgramConfig("https://api.deepgram.com/v1/listen", "DG_KEY")
        )
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=True
        ):
            audio = Path(directory) / "speech.wav"
            audio.touch()
            with self.assertRaisesRegex(TranscriptionError, "DG_KEY"):
                await provider.transcribe(audio)


class WhisperProviderTests(unittest.TestCase):
    def test_status_reports_missing_command_and_model(self):
        provider = WhisperCppSTTProvider(
            WhisperCppConfig(Path("/definitely/missing/model.bin"), "missing-whisper")
        )
        with patch("shutil.which", return_value=None):
            errors = provider.status_errors()
        self.assertEqual(len(errors), 2)
        self.assertIn("command not found", errors[0])
        self.assertIn("model not found", errors[1])


if __name__ == "__main__":
    unittest.main()
