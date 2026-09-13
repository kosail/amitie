import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from config import Settings
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from providers.base import LLMResult, Usage
from providers.voice import SynthesisResult


class FakeTTS:
    name = "elevenlabs"

    async def synthesize(self, text, voice_id="", speed=1.0):
        return SynthesisResult(b"MP3", "audio/mpeg", voice_id or "v", self.name)


class NullProvider:
    name = "null"
    model = "null"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        return LLMResult(text="", tool_calls=(), usage=Usage(), provider="null", model="null")


def _seed(path: str) -> None:
    async def run() -> None:
        database = LocalSQLiteDatabase(path)
        await apply_schema(database)
        await seed(database)
        await database.close()

    asyncio.run(run())


class AgentGreetingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "greeting.sqlite3")
        _seed(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _app(self):
        return create_app(
            provider=NullProvider(),
            settings=Settings(database_path=self.db_path),
            tts=FakeTTS(),
        )

    def _session(self, client: TestClient, user_id: str) -> str:
        response = client.post("/api/session", json={"user_id": user_id})
        self.assertEqual(response.status_code, 200)
        return response.json()["session_id"]

    def test_accessible_greeting_returns_audio(self) -> None:
        with TestClient(self._app()) as client:
            session_id = self._session(client, "u_don")
            response = client.post("/api/agent/greeting", json={"session_id": session_id})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("Don", body["assistant_text"])
        self.assertIn("Luna", body["assistant_text"])
        self.assertNotIn("La Mesa", body["assistant_text"])
        self.assertTrue(body["audio_ref"].startswith("/api/audio/"))
        self.assertEqual(body["a2ui"], [])
        self.assertIsNone(body["surface_id"])

    def test_standard_greeting_has_no_audio(self) -> None:
        with TestClient(self._app()) as client:
            session_id = self._session(client, "u_ana")
            response = client.post("/api/agent/greeting", json={"session_id": session_id})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("Ana", body["assistant_text"])
        self.assertIn("Luna", body["assistant_text"])
        self.assertIn("asesora", body["assistant_text"])
        self.assertNotIn("La Mesa", body["assistant_text"])
        self.assertIsNone(body["audio_ref"])

    def test_unknown_session_is_404(self) -> None:
        with TestClient(self._app()) as client:
            response = client.post(
                "/api/agent/greeting", json={"session_id": "sess_does_not_exist"}
            )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
