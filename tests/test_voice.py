import asyncio
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from numan.voice import (
    AudioAsset,
    CachedVoiceProvider,
    EdgeTTSVoiceProvider,
    KokoroVoiceProvider,
    PiperVoiceProvider,
    RoutingVoiceProvider,
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

    async def test_piper_model_is_resident_and_output_is_postprocessed(self):
        class FakePiper:
            def synthesize_wav(self, text, wav_file, **kwargs):
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(22_050)
                wav_file.writeframes(b"\0\0" * 20)

        loads = []
        profile = VoiceProfile("grog", "", provider="piper", model=Path("grog.onnx"))
        provider = PiperVoiceProvider(
            {"grog": profile},
            voice_loader=lambda item: loads.append(item.id) or FakePiper(),
        )

        async def fake_ffmpeg(*args):
            Path(args[-1]).write_bytes(b"RIFF-local-piper")

        provider._run = AsyncMock(side_effect=fake_ffmpeg)
        first = await provider.synthesize("Ahoy", "grog")
        second = await provider.synthesize("Again", "grog")
        self.assertEqual(loads, ["grog"])
        self.assertEqual(first.path.read_bytes(), b"RIFF-local-piper")
        first.path.unlink()
        second.path.unlink()

    async def test_kokoro_session_is_shared_by_profiles_using_same_bundle(self):
        import numpy as np

        class FakeKokoro:
            def create(self, text, **kwargs):
                return np.zeros(20, dtype=np.float32), 24_000

        loads = []
        common = {"provider": "kokoro", "model": Path("kokoro.onnx"),
                  "voices": Path("voices.bin")}
        profiles = {
            "grog": VoiceProfile("grog", "am_adam", **common),
            "polly": VoiceProfile("polly", "af_sarah", **common),
        }
        provider = KokoroVoiceProvider(
            profiles, model_loader=lambda item: loads.append(item.id) or FakeKokoro()
        )

        async def fake_ffmpeg(*args):
            Path(args[-1]).write_bytes(b"RIFF-local-kokoro")

        provider._run = AsyncMock(side_effect=fake_ffmpeg)
        asset = await provider.synthesize("Hello", "polly")
        self.assertEqual(loads, ["grog"])
        self.assertEqual(asset.path.read_bytes(), b"RIFF-local-kokoro")
        asset.path.unlink()

    async def test_routing_provider_selects_profile_engine(self):
        piper = AsyncMock()
        piper.synthesize.return_value = AudioAsset(Path("piper.wav"))
        kokoro = AsyncMock()
        kokoro.synthesize.return_value = AudioAsset(Path("kokoro.wav"))
        router = RoutingVoiceProvider(
            {"piper": piper, "kokoro": kokoro},
            {"grog": "piper", "polly": "kokoro"},
        )
        result = await router.synthesize("Hello", "polly")
        self.assertEqual(result.path, Path("kokoro.wav"))
        kokoro.synthesize.assert_awaited_once_with("Hello", "polly")

    async def test_rendered_wav_cache_avoids_repeated_synthesis(self):
        with tempfile.TemporaryDirectory() as directory:
            rendered = Path(directory) / "rendered.wav"
            with wave.open(str(rendered), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24_000)
                wav_file.writeframes(b"\0\0" * 20)
            upstream = AsyncMock()
            upstream.synthesize.return_value = AudioAsset(rendered, owned=False)
            profile = VoiceProfile("grog", "am_adam", provider="kokoro")
            provider = CachedVoiceProvider(
                upstream, {"grog": profile}, cache_dir=Path(directory) / "cache"
            )

            first = await provider.synthesize("Same line", "grog")
            second = await provider.synthesize("Same line", "grog")

            self.assertEqual(first.path, second.path)
            self.assertFalse(first.owned)
            self.assertEqual(upstream.synthesize.await_count, 1)


if __name__ == "__main__":
    unittest.main()
