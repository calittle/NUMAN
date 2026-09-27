import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from numan.voice import (
    EdgeTTSVoiceProvider,
    VoiceProfile,
    VoiceProviderError,
    tiki_console_filter,
)


class VoiceProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_tiki_console_builds_expected_filter(self):
        self.assertEqual(
            tiki_console_filter(
                sample_rate=24_000,
                perch_pitch_semitones=4,
                barrel_chest_hz=220,
                barrel_chest_db=6,
                barrel_chest_width=1,
                beak_bite_hz=3150,
                beak_bite_db=20,
                beak_bite_width=0.5,
                feather_sparkle_hz=6000,
                feather_sparkle_db=12,
                coconut_radio_bits=6,
                rum_barrel_lufs=-14,
            ),
            "asetrate=24000*2^(4/12),aresample=24000,atempo=1/2^(4/12),"
            "equalizer=f=220:t=q:w=1:g=6,"
            "equalizer=f=3150:t=q:w=0.5:g=20,"
            "equalizer=f=6000:t=q:w=1:g=12,"
            "acrusher=bits=6:mode=log:aa=1,loudnorm=I=-14:LRA=7:TP=-1.5",
        )

    async def test_edge_prosody_controls_are_forwarded(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = VoiceProfile(
                "grog", "en-GB-RyanNeural",
                rate="-8%", volume="+5%", pitch="-20Hz",
            )
            provider = EdgeTTSVoiceProvider({"grog": profile}, work_dir=directory)

            async def render(*args):
                Path(args[-1]).write_bytes(b"audio")

            provider._run = AsyncMock(side_effect=render)
            asset = await provider.synthesize("Ahoy", "grog")
            edge_args = provider._run.await_args_list[0].args
            self.assertIn("--rate=-8%", edge_args)
            self.assertIn("--volume=+5%", edge_args)
            self.assertIn("--pitch=-20Hz", edge_args)
            asset.path.unlink()

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
