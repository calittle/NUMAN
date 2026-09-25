import unittest
from unittest.mock import patch

from numan.server import live_from_environment


class ServerConfigurationTests(unittest.TestCase):
    def test_live_mode_is_explicitly_enabled(self):
        for value in ("1", "true", "YES", "on"):
            with self.subTest(value=value), patch.dict(
                "os.environ", {"NUMAN_LIVE": value}, clear=True
            ):
                self.assertTrue(live_from_environment())

    def test_safe_mode_remains_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(live_from_environment())


if __name__ == "__main__":
    unittest.main()
