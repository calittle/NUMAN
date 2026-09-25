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
        self.assertEqual(body["response"], "Welcome to the bar.")
        self.assertEqual(body["source"], "routine")
        self.assertEqual(body["conversation_id"], "table-4")

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
