import unittest
from dataclasses import replace

from numan.application import PROJECT_ROOT, build_application
from numan.configuration import LORTriggerConfig, load_config
from numan.show_control import (
    FakeLightORamaProvider,
    LORTrigger,
    LightORamaOSCTriggerProvider,
    ShowAction,
    encode_osc_trigger,
)


class LightORamaOSCTests(unittest.IsolatedAsyncioTestCase):
    def test_trigger_packet_matches_osc_integer_encoding(self):
        packet = encode_osc_trigger(LORTrigger(0, 17, 512))
        self.assertEqual(
            packet,
            b"/trigger\0\0\0\0"
            + b",iii\0\0\0\0"
            + b"\0\0\0\0"
            + b"\0\0\0\x11"
            + b"\0\0\x02\0",
        )

    async def test_provider_maps_semantic_action_and_sends_to_destination(self):
        sent = []

        async def capture(packet, host, port):
            sent.append((packet, host, port))

        provider = LightORamaOSCTriggerProvider(
            "127.0.0.1", 9000, {"storm": LORTrigger(0, 1, 3)}, send=capture
        )
        await provider.trigger(ShowAction("storm"))
        self.assertEqual(sent[0][1:], ("127.0.0.1", 9000))
        self.assertEqual(sent[0][0], encode_osc_trigger(LORTrigger(0, 1, 3)))

    async def test_unmapped_action_is_rejected_without_sending(self):
        sent = []

        async def capture(packet, host, port):
            sent.append((packet, host, port))

        provider = LightORamaOSCTriggerProvider(
            "127.0.0.1", 9000, {}, send=capture
        )
        with self.assertRaisesRegex(ValueError, "no LOR trigger"):
            await provider.trigger(ShowAction("storm"))
        self.assertEqual(sent, [])

    def test_advanced_provider_configuration_and_safe_mode(self):
        config = load_config(PROJECT_ROOT / "config/numan.toml")
        triggers = {
            action: LORTriggerConfig(0, 1, circuit)
            for circuit, action in enumerate(
                sorted(config.show_control.allowed_actions), start=1
            )
        }
        show_control = replace(
            config.show_control,
            provider="lor-osc-trigger",
            port=9000,
            triggers=triggers,
        )
        configured = replace(config, show_control=show_control)
        configured.validate()
        application = build_application(configured, live=False)
        self.assertIsInstance(application.show_control, FakeLightORamaProvider)


if __name__ == "__main__":
    unittest.main()
