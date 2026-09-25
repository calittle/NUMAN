import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from numan.voice import EdgeTTSVoiceProvider, VoiceProviderError


class VoiceProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_profile_fails_before_spawning_tools(self):
        provider = EdgeTTSVoiceProvider({})
        with self.assertRaisesRegex(VoiceProviderError, "unknown voice profile"):
            await provider.synthesize("Hello", "missing")

    async def test_empty_text_is_rejected(self):
        provider = EdgeTTSVoiceProvider({})
        with self.assertRaisesRegex(VoiceProviderError, "empty"):
            await provider.synthesize("  ", "missing")

    async def test_command_timeout_terminates_child(self):
        process = MagicMock()
        process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        process.wait = AsyncMock(return_value=0)
        process.returncode = None
        provider = EdgeTTSVoiceProvider({}, command_timeout_s=0.01)
        with patch("asyncio.create_subprocess_exec", return_value=process):
            with self.assertRaisesRegex(VoiceProviderError, "timed out"):
                await provider._run("edge-tts")
        process.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
