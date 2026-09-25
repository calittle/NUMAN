import io
import json
import unittest
from unittest.mock import patch

from numan.conversations import ConversationTurn, TurnRole
from numan.engine.models import Character, Utterance
from numan.engine.providers import OllamaConfig, OllamaLLMProvider


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class OllamaProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = OllamaLLMProvider(
            OllamaConfig("http://127.0.0.1:11434/api", "llama3.2:3b")
        )
        self.character = Character("nigel", "Nigel", "Be terse.", "voice")

    async def test_chat_uses_native_non_streaming_api_and_history(self):
        captured = {}

        def urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            return _Response(b'{"message":{"content":"  Quite.  "}}')

        history = (ConversationTurn(TurnRole.USER, "Earlier", None),)
        with patch("urllib.request.urlopen", side_effect=urlopen):
            result = await self.provider.complete(
                Utterance("Now?", "nigel", "one"), self.character, history
            )

        self.assertEqual(result, "Quite.")
        self.assertEqual(captured["url"], "http://127.0.0.1:11434/api/chat")
        self.assertFalse(captured["body"]["stream"])
        self.assertEqual(captured["body"]["keep_alive"], "30m")
        self.assertEqual(captured["body"]["options"]["num_predict"], 80)
        self.assertEqual(
            captured["body"]["messages"],
            [
                {"role": "system", "content": "Be terse."},
                {"role": "user", "content": "Earlier"},
                {"role": "user", "content": "Now?"},
            ],
        )

    async def test_lists_installed_models(self):
        response = b'{"models":[{"name":"llama3.2:3b"},{"name":"gemma3:4b"}]}'
        with patch("urllib.request.urlopen", return_value=_Response(response)):
            self.assertEqual(
                await self.provider.list_models(), ("llama3.2:3b", "gemma3:4b")
            )


if __name__ == "__main__":
    unittest.main()
