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
        show = (await self.client.get("/show")).json()
        self.assertEqual(show["provider"], "fake")
        self.assertTrue(show["hardware_safe"])
        self.assertIn("storm", show["characters"]["nigel"])

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

    async def test_show_routine_exposes_semantic_action(self):
        response = await self.client.post("/ask", json={
            "question": "Bring on a storm",
            "character_id": "polly",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "routine")
        self.assertEqual(body["show_actions"], ["storm"])

    async def test_delayed_drink_cue_can_be_inspected_and_cancelled(self):
        response = await self.client.post("/ask", json={
            "question": "I want a Jet Pilot",
            "character_id": "polly",
        })
        body = response.json()
        cue = body["scheduled_actions"][0]
        self.assertEqual(cue["action"], "present_jet_pilot")
        self.assertEqual(cue["delay_seconds"], 120)
        self.assertEqual(cue["status"], "scheduled")
        pending = (await self.client.get("/show/cues")).json()
        self.assertIn(cue["id"], {item["id"] for item in pending})
        cancelled = await self.client.delete(f"/show/cues/{cue['id']}")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], "cancelled")

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
