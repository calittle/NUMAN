import unittest

from numan.application import PROJECT_ROOT
from numan.pre_render import deterministic_responses, pre_render_responses
from numan.voice import AudioAsset


class _RecordingVoice:
    def __init__(self):
        self.calls = []

    async def synthesize(self, text, profile_id):
        self.calls.append((text, profile_id))
        return AudioAsset(PROJECT_ROOT / "unused.wav")


class PreRenderTests(unittest.IsolatedAsyncioTestCase):
    def test_deterministic_content_includes_pools_recipes_and_presentations(self):
        responses = deterministic_responses(PROJECT_ROOT)
        self.assertIn("Welcome to the bar. Mind the rigging and lower your expectations.", responses["grog"])
        self.assertTrue(any(value.startswith("A Mai Tai uses") for value in responses["polly"]))
        self.assertIn(
            "One Jet Pilot! Your boarding spectacle will begin shortly.",
            responses["polly"],
        )

    async def test_pre_render_uses_each_characters_selected_profile(self):
        provider = _RecordingVoice()
        counts = await pre_render_responses(
            PROJECT_ROOT, provider, {"grog": "grog-local", "polly": "polly-local"}
        )
        self.assertEqual(len(provider.calls), sum(counts.values()))
        self.assertIn("grog-local", {profile for _, profile in provider.calls})
        self.assertIn("polly-local", {profile for _, profile in provider.calls})


if __name__ == "__main__":
    unittest.main()
