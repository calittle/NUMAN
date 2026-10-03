import tempfile
import unittest
from pathlib import Path

from numan.application import PROJECT_ROOT, build_application, live_environment_errors
from numan.configuration import ConfigurationError, load_config


class ConfigurationTests(unittest.TestCase):
    def test_project_configuration_is_valid_and_composable(self):
        config = load_config(PROJECT_ROOT / "config/numan.toml")
        application = build_application(config, live=False)
        self.assertEqual(config.default_character, "grog")
        self.assertEqual(config.microphone.end_silence_ms, 750)
        self.assertEqual(application.actors.get("grog-dev").character_id, "grog")
        self.assertEqual(set(application.characters), {"grog", "polly"})
        self.assertEqual(application.actors.get("polly-dev").character_id, "polly")
        self.assertEqual(
            config.voices["grog-piper-alan-shrill"].tiki_console.coconut_radio_bits,
            9,
        )
        self.assertEqual(config.voices["grog-piper-alan-shrill"].provider, "piper")
        self.assertEqual(
            config.voices["grog-piper-alan-shrill"].tiki_console.barrel_chest_db,
            6,
        )
        self.assertEqual(config.voices["polly-kokoro-sarah-bright"].provider, "kokoro")
        self.assertEqual(
            config.voices["polly-piper-lessac-bright"].tiki_console.coconut_radio_bits,
            11,
        )
        self.assertEqual(config.characters["polly"].voice_profile, "polly-piper-lessac-bright")
        self.assertEqual(config.voices["polly-piper-lessac-bright"].provider, "piper")
        for character in config.characters.values():
            prompt = character.system_prompt.casefold()
            self.assertIn("sentient", prompt)
            self.assertIn("macaw", prompt)
            self.assertIn("the kraken's curse", prompt)
            self.assertIn("feathers", prompt)
            self.assertIn("wings", prompt)
            self.assertIn("beak", prompt)
            self.assertIn("talons", prompt)

    def test_unknown_actor_route_is_rejected(self):
        source = (PROJECT_ROOT / "config/numan.toml").read_text(encoding="utf-8")
        source = source.replace(
            'audio_route = "development-default"', 'audio_route = "missing"'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "unknown route"):
                load_config(path)

    def test_system_backend_cannot_claim_named_device(self):
        source = (PROJECT_ROOT / "config/numan.toml").read_text(encoding="utf-8")
        source = source.replace('device = "system-default"', 'device = "Bird USB"')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "cannot select"):
                load_config(path)

    def test_live_environment_reports_missing_tools_without_crashing(self):
        config = load_config(PROJECT_ROOT / "config/numan.toml")
        self.assertIsInstance(live_environment_errors(config), list)

    def test_invalid_voice_prosody_is_rejected(self):
        source = (PROJECT_ROOT / "config/numan.toml").read_text(encoding="utf-8")
        source = source.replace('provider = "piper"', 'provider = "mystery"', 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "unsupported provider"):
                load_config(path)

    def test_local_voice_provider_fields_are_parsed(self):
        source = (PROJECT_ROOT / "config/numan.toml").read_text(encoding="utf-8")
        source = source.replace('voice = "af_sarah"', 'voice = "am_adam"', 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.toml"
            path.write_text(source, encoding="utf-8")
            config = load_config(path)
        voice = config.voices["polly-kokoro-sarah-bright"]
        self.assertEqual(voice.provider, "kokoro")
        self.assertEqual(voice.model, "models/tts/kokoro/kokoro-v1.0.onnx")
        self.assertEqual(voice.voices, "models/tts/kokoro/voices-v1.0.bin")

    def test_local_provider_requires_model_paths(self):
        source = (PROJECT_ROOT / "config/numan.toml").read_text(encoding="utf-8")
        source = source.replace(
            'model = "models/tts/piper/en_GB-alan-medium.onnx"', 'model = ""', 1
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "Piper provider requires model"):
                load_config(path)

    def test_invalid_microphone_end_silence_is_rejected(self):
        source = (PROJECT_ROOT / "config/numan.toml").read_text(encoding="utf-8")
        source = source.replace("end_silence_ms = 750", "end_silence_ms = 100")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "end_silence_ms"):
                load_config(path)

    def test_character_cannot_reference_unavailable_show_action(self):
        source = (PROJECT_ROOT / "config/numan.toml").read_text(encoding="utf-8")
        source = source.replace(
            'allowed_actions = ["storm", "lightning", "volcano_rumble", "blackout", "present_jet_pilot", "present_suffering_bastard"]',
            'allowed_actions = ["storm", "lightning", "volcano_rumble", "present_jet_pilot", "present_suffering_bastard"]',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "unavailable show actions"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
