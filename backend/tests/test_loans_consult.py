"""Loans & credits consult: structured call, confidence gate, placeholders."""

import asyncio
import json
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

COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["t"], "gap": 12},
    {"id": "t", "component": "Text", "text": "Monto solicitado: {{loan.amount}}"},
]
DATA_MODEL = {"loan": {"amount": 50000}}


class FakeTTS:
    name = "elevenlabs"

    async def synthesize(self, text, voice_id="", speed=1.0):
        return SynthesisResult(b"MP3", "audio/mpeg", voice_id or "v", self.name)


class QueueProvider:
    name = "gemini"
    model = "gemini-3.6-flash"

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = 0

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        self.calls += 1
        payload = self._payloads.pop(0) if self._payloads else {"response_text": "", "confidence": 0}
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return LLMResult(text=text, tool_calls=(), usage=Usage(), provider="gemini", model="gemini-3.6-flash")


def _terminal(response_text, confidence, components=None, data_model=None):
    return {
        "response_text": response_text,
        "confidence": confidence,
        "terminal_response": (
            {
                "catalog_id": "amitie.standard.v1",
                "components": components or COMPONENTS,
                "data_model": data_model or DATA_MODEL,
            }
            if confidence > 0.80
            else None
        ),
    }


class LoansConsultTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "loans.sqlite3")

        async def prep() -> None:
            database = LocalSQLiteDatabase(self.db_path)
            await apply_schema(database)
            await seed(database)
            await database.close()

        asyncio.run(prep())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _app(self, payloads):
        provider = QueueProvider(payloads)
        settings = Settings(
            database_path=self.db_path, audio_cache_dir=str(Path(self._tmp.name) / "audio")
        )
        app = create_app(provider=provider, settings=settings, tts=FakeTTS())
        self.provider = provider
        return app

    def test_greeting_returns_session_and_audio(self) -> None:
        with TestClient(self._app([])) as client:
            body = client.post("/api/loans/greeting", json={"user_id": "u_ana"}).json()
        self.assertEqual(body["status"], "ok", body)
        self.assertTrue(body["session_id"].startswith("sess_"))
        self.assertTrue(body["response_text"])
        self.assertTrue(body["audio_ref"].startswith("/api/audio/"))
        self.assertIsNone(body["terminal_response"])

    def test_non_terminal_turn(self) -> None:
        with TestClient(self._app([_terminal("¿Cuánto necesitas?", 0.4)])) as client:
            session = client.post("/api/loans/greeting", json={"user_id": "u_ana"}).json()["session_id"]
            body = client.post(
                "/api/loans/consult",
                json={"session_id": session, "text": "quiero un crédito"},
            ).json()
        self.assertEqual(body["status"], "ok", body)
        self.assertEqual(body["confidence"], 0.4)
        self.assertIsNone(body["terminal_response"])
        self.assertTrue(body["audio_ref"])

    def test_terminal_turn_persists_and_placeholders_resolve(self) -> None:
        with TestClient(self._app([_terminal("Aquí está tu propuesta.", 0.9)])) as client:
            session = client.post("/api/loans/greeting", json={"user_id": "u_ana"}).json()["session_id"]
            body = client.post(
                "/api/loans/consult",
                json={"session_id": session, "text": "crédito de 50000"},
            ).json()
            self.assertEqual(body["status"], "ok", body)
            self.assertEqual(body["terminal_response"]["catalog_id"], "amitie.standard.v1")
            loan_id = body["loan_request_id"]

            fetched = client.get(f"/api/loans/{loan_id}").json()
        self.assertEqual(fetched["status"], "ok", fetched)
        self.assertIsNotNone(fetched["terminal_response"])
        components = next(
            m for m in fetched["terminal_response"]["a2ui"] if "updateComponents" in m
        )["updateComponents"]["components"]
        text_component = next(c for c in components if c["component"] == "Text")
        self.assertEqual(text_component["text"], "Monto solicitado: 50000")

    def test_invalid_terminal_retries_then_succeeds(self) -> None:
        bad = {
            "response_text": "…",
            "confidence": 0.9,
            "terminal_response": {
                "catalog_id": "amitie.standard.v1",
                "components": [{"id": "x", "component": "Nope"}],
                "data_model": {},
            },
        }
        with TestClient(self._app([bad, _terminal("Corregido.", 0.9)])) as client:
            session = client.post("/api/loans/greeting", json={"user_id": "u_ana"}).json()["session_id"]
            body = client.post(
                "/api/loans/consult",
                json={"session_id": session, "text": "crédito"},
            ).json()
        self.assertEqual(body["status"], "ok", body)
        self.assertIsNotNone(body["terminal_response"])
        self.assertEqual(self.provider.calls, 2)

    def test_consult_unknown_session_404(self) -> None:
        with TestClient(self._app([])) as client:
            response = client.post(
                "/api/loans/consult", json={"session_id": "nope", "text": "hola"}
            )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
