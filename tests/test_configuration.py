import tempfile
import unittest
from pathlib import Path

from numan.application import PROJECT_ROOT, build_application, live_environment_errors
from numan.configuration import ConfigurationError, load_config


class ConfigurationTests(unittest.TestCase):
    def test_project_configuration_is_valid_and_composable(self):
        config = load_config(PROJECT_ROOT / "config/numan.toml")
        application = build_application(config, live=False)
        self.assertEqual(config.default_character, "nigel")
        self.assertEqual(application.actors.get("nigel-dev").character_id, "nigel")
        self.assertEqual(set(application.characters), {"nigel", "polly"})
        self.assertEqual(application.actors.get("polly-dev").character_id, "polly")
        self.assertEqual(
            config.voices["nigel-edge-ryan-shrill"].tiki_console.coconut_radio_bits,
            6,
        )

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
