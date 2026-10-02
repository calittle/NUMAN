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
    WhisperServerConfig,
    WhisperServerSTTProvider,
    resolve_whisper_command,
)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class DeepgramProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_transcribes_wav_and_uses_token_auth(self):
        payload = {
            "results": {"channels": [{"alternatives": [{"transcript": "Hello Captain Grog"}]}]}
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

        self.assertEqual(text, "Hello Captain Grog")
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
    def test_finds_portable_windows_command_next_to_python(self):
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / "python.exe"
            command = Path(directory) / "whisper-cli.exe"
            command.touch()
            with patch("numan.transcription.shutil.which", return_value=None), patch(
                "numan.transcription.sys.platform", "win32"
            ), patch("numan.transcription.sys.executable", str(python)):
                self.assertEqual(resolve_whisper_command("whisper-cli"), command)

    def test_status_reports_missing_command_and_model(self):
        provider = WhisperCppSTTProvider(
            WhisperCppConfig(Path("/definitely/missing/model.bin"), "missing-whisper")
        )
        with patch("shutil.which", return_value=None):
            errors = provider.status_errors()
        self.assertEqual(len(errors), 2)
        self.assertIn("command not found", errors[0])
        self.assertIn("model not found", errors[1])

    def test_server_request_uses_local_multipart_endpoint(self):
        captured = {}

        def urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["content_type"] = request.headers["Content-type"]
            captured["body"] = request.data
            return _Response(json.dumps({"text": " Welcome aboard.\n"}).encode())

        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "speech.wav"
            audio.write_bytes(b"RIFF-local")
            provider = WhisperServerSTTProvider(
                WhisperServerConfig(Path("model.bin"), host="127.0.0.1", port=8178)
            )
            with patch("urllib.request.urlopen", side_effect=urlopen):
                text = provider._transcribe_sync(audio)

        self.assertEqual(text, "Welcome aboard.")
        self.assertEqual(captured["url"], "http://127.0.0.1:8178/inference")
        self.assertIn("multipart/form-data", captured["content_type"])
        self.assertIn(b"RIFF-local", captured["body"])


if __name__ == "__main__":
    unittest.main()
