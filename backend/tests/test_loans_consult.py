"""Loans & credits consult: greeting, structured call, multipart audio, placeholders."""

import asyncio
import email
import json
import re
import tempfile
import unittest
from email import policy
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
    {"id": "root", "component": "Column", "children": ["offer", "t"], "gap": 12},
    {
        "id": "offer",
        "component": "LoanOffer",
        "amount": {"path": "/loan/amount"},
        "apr": {"path": "/loan/apr"},
        "months": {"path": "/loan/termMonths"},
        "monthlyPayment": {"path": "/loan/monthlyPayment"},
        "totalInterest": {"path": "/loan/totalInterest"},
        "cat": {"path": "/loan/cat"},
        "schedule": {"path": "/loan/schedule"},
        "action": {"event": {"name": "request_loan", "context": {}}},
    },
    {"id": "t", "component": "Text", "text": "Monto: {{loan.amount}}"},
]


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


class CapturingProvider:
    name = "gemini"
    model = "gemini-3.6-flash"

    def __init__(self, payload):
        self._payload = payload
        self.messages = []

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        self.messages = list(messages)
        return LLMResult(
            text=json.dumps(self._payload),
            tool_calls=(),
            usage=Usage(),
            provider="gemini",
            model="gemini-3.6-flash",
        )


def parse_multipart(response):
    """Return (payload_json, audio_bytes) from a multipart/form-data response."""
    content_type = response.headers["content-type"]
    raw = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + response.content
    message = email.message_from_bytes(raw, policy=policy.default)
    payload = None
    audio = None
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        name = part.get_param("name", header="content-disposition")
        data = part.get_payload(decode=True) or b""
        if name == "payload":
            payload = json.loads(data.decode("utf-8"))
        elif name == "audio":
            audio = data
    return payload, audio


def _terminal(response_text, confidence):
    return {
        "response_text": response_text,
        "confidence": confidence,
        "terminal_response": (
            {
                "catalog_id": "amitie.standard.v1",
                "components": COMPONENTS,
                "data_model": {},
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

    def _app_with(self, provider):
        settings = Settings(
            database_path=self.db_path, audio_cache_dir=str(Path(self._tmp.name) / "audio")
        )
        app = create_app(provider=provider, settings=settings, tts=FakeTTS())
        self.provider = provider
        return app

    def _app(self, payloads):
        return self._app_with(QueueProvider(payloads))

    def test_greeting_is_personalized_and_returns_mp3(self) -> None:
        with TestClient(self._app([])) as client:
            response = client.post("/api/loans/greeting", json={"user_id": "u_ana"})
        self.assertTrue(response.headers["content-type"].startswith("multipart/form-data"))
        payload, audio = parse_multipart(response)
        self.assertEqual(payload["status"], "ok", payload)
        self.assertTrue(payload["session_id"].startswith("sess_"))
        self.assertEqual(payload["response_text"], "¿En qué te puedo ayudar hoy, Ana?")
        self.assertIsNone(payload["terminal_response"])
        self.assertEqual(audio, b"MP3")

    def test_non_terminal_turn_returns_text_and_mp3(self) -> None:
        with TestClient(self._app([_terminal("¿Cuánto necesitas?", 0.4)])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            response = client.post(
                "/api/loans/consult",
                json={"session_id": session, "text": "quiero un crédito"},
            )
        payload, audio = parse_multipart(response)
        self.assertEqual(payload["status"], "ok", payload)
        self.assertEqual(payload["confidence"], 0.4)
        self.assertIsNone(payload["terminal_response"])
        self.assertTrue(payload["audio_ref"])
        self.assertEqual(audio, b"MP3")

    def test_terminal_turn_persists_and_placeholders_resolve(self) -> None:
        with TestClient(self._app([_terminal("Aquí está tu propuesta.", 0.9)])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            payload, audio = parse_multipart(
                client.post(
                    "/api/loans/consult",
                    json={"session_id": session, "text": "crédito de 50000"},
                )
            )
            self.assertEqual(payload["status"], "ok", payload)
            self.assertEqual(audio, b"MP3")
            terminal = payload["terminal_response"]
            self.assertIsNotNone(terminal, payload)
            loan_id = payload["loan_request_id"]
            fetched = client.get(f"/api/loans/{loan_id}").json()
        self.assertEqual(fetched["status"], "ok", fetched)
        components = next(
            m for m in fetched["terminal_response"]["a2ui"] if "updateComponents" in m
        )["updateComponents"]["components"]
        offer = next(c for c in components if c["component"] == "LoanOffer")
        self.assertIsInstance(offer["amount"], (int, float))
        self.assertGreater(offer["amount"], 0)
        text_component = next(c for c in components if c["component"] == "Text")
        self.assertGreater(float(re.search(r"\d+", text_component["text"]).group()), 0)

    def test_prompt_includes_offer_and_analysis(self) -> None:
        provider = CapturingProvider(_terminal("ok", 0.4))
        with TestClient(self._app_with(provider)) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            client.post(
                "/api/loans/consult", json={"session_id": session, "text": "crédito"}
            )
        joined = " ".join(message.content or "" for message in provider.messages)
        self.assertIn("Analisis determinista", joined)
        self.assertIn("OFERTA DETERMINISTA", joined)
        self.assertIn("LoanOffer", joined)

    def test_prompt_adapts_to_low_literacy_audience(self) -> None:
        provider = CapturingProvider(_terminal("Listo.", 0.9))
        with TestClient(self._app_with(provider)) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            payload, _audio = parse_multipart(
                client.post(
                    "/api/loans/consult",
                    json={"session_id": session, "text": "quiero un crédito"},
                )
            )
        joined = " ".join(message.content or "" for message in provider.messages)
        self.assertIn("ADAPTACIÓN DE AUDIENCIA", joined)
        self.assertIn("BÁSICA", joined)
        self.assertIsNotNone(payload["terminal_response"])
        data_model = next(
            m["updateDataModel"]["value"]
            for m in payload["terminal_response"]["a2ui"]
            if "updateDataModel" in m
        )
        self.assertEqual(data_model["audience"]["level"], "simple")

    def test_missing_loan_offer_is_rejected(self) -> None:
        bad = {
            "response_text": "…",
            "confidence": 0.9,
            "terminal_response": {
                "catalog_id": "amitie.standard.v1",
                "components": [
                    {"id": "root", "component": "Column", "children": ["t"], "gap": 12},
                    {"id": "t", "component": "Text", "text": "Monto: {{loan.amount}}"},
                ],
                "data_model": {},
            },
        }
        with TestClient(self._app([bad, bad])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            payload, _ = parse_multipart(
                client.post(
                    "/api/loans/consult", json={"session_id": session, "text": "crédito"}
                )
            )
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_code"], "agent_error")

    def test_consult_unknown_session_404(self) -> None:
        with TestClient(self._app([])) as client:
            response = client.post(
                "/api/loans/consult", json={"session_id": "nope", "text": "hola"}
            )
        self.assertEqual(response.status_code, 404)

    def test_create_loan_disburses(self) -> None:
        with TestClient(self._app([])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            _ = session
            response = client.post(
                "/api/loans",
                json={"user_id": "u_don", "amount": 10000.0, "loan_request_id": "loan_test"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        loan = response.json()["loan"]
        self.assertEqual(loan["amount"], 10000.0)
        self.assertGreater(loan["monthlyPayment"], 0)
        self.assertGreater(len(loan["schedule"]), 0)


if __name__ == "__main__":
    unittest.main()
