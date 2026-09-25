import unittest

import httpx

from numan.api import create_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        transport = httpx.ASGITransport(app=create_app())
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_health_and_inventory(self):
        self.assertEqual(
            (await self.client.get("/health")).json(),
            {"status": "ok", "live": False, "audio_backend": "fake"},
        )
        self.assertEqual((await self.client.get("/characters")).json()[0]["id"], "nigel")
        self.assertEqual((await self.client.get("/actors")).json()[0]["id"], "nigel-dev")

    async def test_safe_ask_endpoint(self):
        response = await self.client.post("/ask", json={
            "question": "Hello", "conversation_id": "table-4",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["response"], {
            "Welcome to the bar. Mind the rigging and lower your expectations.",
            "Ahoy. If you're here for charm, Polly's over there. If you're here for rum, we may talk.",
            "Well, look what the tide dragged in. Pull up a stool.",
            "Evening. State your poison before I die of suspense.",
            "Welcome aboard, mate. Your first bad decision is always the hardest.",
            "Hello there. Don't look so nervous; I only bite corks.",
            "Good to see you. Not that I'll be making a habit of saying so.",
            "Come in, come in. The rum's warm and the company is questionable.",
        })
        self.assertEqual(body["source"], "routine")
        self.assertEqual(body["conversation_id"], "table-4")

    async def test_character_selects_its_actor_and_private_cache(self):
        response = await self.client.post("/ask", json={
            "question": "Who are you?",
            "character_id": "polly",
            "conversation_id": "table-4",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["actor_id"], "polly-dev")
        self.assertEqual(body["route_id"], "polly-development")
        self.assertEqual(body["source"], "exact_cache")
        self.assertTrue(body["response"].startswith("I'm Polly"))

    async def test_ask_validation_and_unknown_actor(self):
        self.assertEqual(
            (await self.client.post("/ask", json={"question": " "})).status_code,
            400,
        )
        self.assertEqual(
            (await self.client.post(
                "/ask", json={"question": "Hello", "actor_id": "missing"}
            )).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
