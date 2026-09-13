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
from engine import loan_offer
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

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
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

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
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
                json={"session_id": session, "text": "quiero un crédito de 5000 para un auto"},
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
                    json={"session_id": session, "text": "crédito de 50000 para mi negocio"},
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
                "/api/loans/consult", json={"session_id": session, "text": "crédito de 5000 para un auto"}
            )
        joined = " ".join(message.content or "" for message in provider.messages)
        self.assertIn("Analisis determinista", joined)
        self.assertIn("OFERTA DETERMINISTA", joined)
        self.assertIn("LoanOffer", joined)
        self.assertIn("Luna", joined)
        self.assertIn("asesora", joined)
        self.assertNotIn("La Mesa", joined)
        # The long per-month schedule is trimmed from the prompt (latency).
        self.assertIn("usa el binding /loan/schedule", joined)

    def test_prompt_adapts_to_low_literacy_audience(self) -> None:
        provider = CapturingProvider(_terminal("Listo.", 0.9))
        with TestClient(self._app_with(provider)) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            payload, _audio = parse_multipart(
                client.post(
                    "/api/loans/consult",
                    json={"session_id": session, "text": "quiero un crédito de 5000 para un auto"},
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

    def test_missing_loan_offer_falls_back_to_deterministic_terminal(self) -> None:
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
        with TestClient(self._app([bad])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            payload, _ = parse_multipart(
                client.post(
                    "/api/loans/consult", json={"session_id": session, "text": "crédito de 5000 para un auto"}
                )
            )
        self.assertEqual(payload["status"], "ok", payload)
        terminal = payload["terminal_response"]
        self.assertIsNotNone(terminal)
        components = next(
            m for m in terminal["a2ui"] if "updateComponents" in m
        )["updateComponents"]["components"]
        offer = next(c for c in components if c["component"] == "LoanOffer")
        self.assertGreater(float(offer["amount"]), 0)

    def test_bare_action_and_placeholders_are_normalized(self) -> None:
        generated = {
            "response_text": "Aquí está tu oferta.",
            "confidence": 0.9,
            "terminal_response": {
                "catalog_id": "amitie.standard.v1",
                "components": [
                    {"id": "root", "component": "Column", "children": ["offer"], "gap": 12},
                    {
                        "id": "offer",
                        "component": "LoanOffer",
                        "amount": "{{loan.amount}}",
                        "apr": "{{loan.apr}}",
                        "months": "{{loan.termMonths}}",
                        "monthlyPayment": "{{loan.monthlyPayment}}",
                        "totalInterest": "{{loan.totalInterest}}",
                        "cat": "{{loan.cat}}",
                        "action": "request_loan",
                    },
                ],
                "data_model": {},
            },
        }
        with TestClient(self._app([generated])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            payload, _ = parse_multipart(
                client.post(
                    "/api/loans/consult", json={"session_id": session, "text": "crédito de 5000 para un auto"}
                )
            )
        self.assertEqual(payload["status"], "ok", payload)
        terminal = payload["terminal_response"]
        self.assertIsNotNone(terminal)
        components = next(
            m for m in terminal["a2ui"] if "updateComponents" in m
        )["updateComponents"]["components"]
        offer = next(c for c in components if c["component"] == "LoanOffer")
        self.assertIsInstance(offer["amount"], (int, float))
        self.assertGreater(offer["amount"], 0)
        self.assertIn("event", offer["action"])
        self.assertEqual(offer["action"]["event"]["name"], "request_loan")

    def test_requested_term_requires_confirmation_then_is_honored(self) -> None:
        with TestClient(self._app([_terminal("Listo, aquí está tu oferta.", 0.9)])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            confirm, _ = parse_multipart(
                client.post(
                    "/api/loans/consult",
                    json={"session_id": session, "text": "quiero un crédito de 5000 a 12 meses"},
                )
            )
            self.assertEqual(confirm["status"], "ok", confirm)
            self.assertIsNone(confirm["terminal_response"])
            self.assertIn("12 meses", confirm["response_text"])
            self.assertEqual(self.provider.calls, 0)  # no LLM turn for the confirmation
            loan_id = confirm["loan_request_id"]

            terminal, _ = parse_multipart(
                client.post(
                    "/api/loans/consult",
                    json={"session_id": session, "text": "sí, confirmo", "loan_request_id": loan_id},
                )
            )
        self.assertEqual(self.provider.calls, 1)
        self.assertIsNotNone(terminal["terminal_response"])
        components = next(
            message
            for message in terminal["terminal_response"]["a2ui"]
            if "updateComponents" in message
        )["updateComponents"]["components"]
        offer = next(c for c in components if c["component"] == "LoanOffer")
        self.assertEqual(int(offer["months"]), 12)

    def test_create_loan_honors_requested_term(self) -> None:
        with TestClient(self._app([])) as client:
            response = client.post(
                "/api/loans",
                json={
                    "user_id": "u_don",
                    "amount": 10000.0,
                    "months": 12,
                    "loan_request_id": "loan_term12",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        loan = response.json()["loan"]
        self.assertEqual(loan["termMonths"], 12)

    def test_vague_turn_asks_for_amount_and_stays_open(self) -> None:
        with TestClient(self._app([])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            payload, audio = parse_multipart(
                client.post(
                    "/api/loans/consult",
                    json={"session_id": session, "text": "quiero un crédito"},
                )
            )
        self.assertEqual(payload["status"], "ok", payload)
        self.assertIsNone(payload["terminal_response"])
        self.assertTrue(payload["response_text"])
        self.assertTrue(payload["audio_ref"])
        self.assertEqual(audio, b"MP3")
        # The intake used the model once for a natural question; no offer was made.
        self.assertEqual(self.provider.calls, 1)

    def test_amount_persists_and_never_jumps_to_max(self) -> None:
        with TestClient(self._app([_terminal("Listo, aquí está tu oferta.", 0.9)])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            first, _ = parse_multipart(
                client.post(
                    "/api/loans/consult",
                    json={"session_id": session, "text": "quiero 5000 a 12 meses"},
                )
            )
            # term confirmation also asks the (missing) purpose
            self.assertIsNone(first["terminal_response"])
            self.assertIn("12 meses", first["response_text"])
            self.assertIn("para qué", first["response_text"])
            loan_id = first["loan_request_id"]

            second, _ = parse_multipart(
                client.post(
                    "/api/loans/consult",
                    json={
                        "session_id": session,
                        "text": "sí, para un auto",
                        "loan_request_id": loan_id,
                    },
                )
            )
        self.assertIsNotNone(second["terminal_response"])
        components = next(
            message
            for message in second["terminal_response"]["a2ui"]
            if "updateComponents" in message
        )["updateComponents"]["components"]
        offer = next(c for c in components if c["component"] == "LoanOffer")
        self.assertEqual(int(offer["months"]), 12)
        # u_don's maximum is far above 5,000: the persisted amount must win.
        self.assertLessEqual(float(offer["amount"]), 5000.0 + 0.01)

    def test_explicit_maximum_is_honored(self) -> None:
        with TestClient(self._app([_terminal("Listo.", 0.9)])) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            payload, _ = parse_multipart(
                client.post(
                    "/api/loans/consult",
                    json={"session_id": session, "text": "dame el máximo, para un negocio"},
                )
            )
        self.assertIsNotNone(payload["terminal_response"])
        components = next(
            message
            for message in payload["terminal_response"]["a2ui"]
            if "updateComponents" in message
        )["updateComponents"]["components"]
        offer = next(c for c in components if c["component"] == "LoanOffer")
        self.assertGreater(float(offer["amount"]), 0)

    def test_fallback_asks_instead_of_max_without_amount(self) -> None:
        from agent import loans_fallback

        result = loans_fallback.build_terminal(
            profile={"name": "Don Miguel"},
            offer={"offer": {"amount": 47500.0}},
            requested_amount=None,
            use_max=False,
        )
        self.assertIsNone(result["terminal_response"])
        self.assertTrue(result["response_text"])

    def test_latency_defaults(self) -> None:
        settings = Settings()
        self.assertGreaterEqual(settings.loans_llm_deadline_seconds, 6.0)
        self.assertGreater(settings.loans_max_tokens, 900)
        self.assertGreater(settings.loans_intake_deadline_seconds, 0)

    def test_llm_timeout_returns_deterministic_fallback(self) -> None:
        class SlowProvider(CapturingProvider):
            async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
                await asyncio.sleep(0.5)
                return await super().generate(
                    messages, tools, response_schema, temperature, max_tokens
                )

        provider = SlowProvider(_terminal("tarde", 0.9))
        settings = Settings(
            database_path=self.db_path,
            audio_cache_dir=str(Path(self._tmp.name) / "audio"),
            loans_llm_deadline_seconds=0.05,
        )
        app = create_app(provider=provider, settings=settings, tts=FakeTTS())
        with TestClient(app) as client:
            session = parse_multipart(
                client.post("/api/loans/greeting", json={"user_id": "u_don"})
            )[0]["session_id"]
            payload, _ = parse_multipart(
                client.post(
                    "/api/loans/consult", json={"session_id": session, "text": "crédito de 5000 para un auto"}
                )
            )
        self.assertEqual(payload["status"], "ok", payload)
        self.assertIsNotNone(payload["terminal_response"])
        components = next(
            message
            for message in payload["terminal_response"]["a2ui"]
            if "updateComponents" in message
        )["updateComponents"]["components"]
        scenario = next(
            component for component in components if component["component"] == "ScenarioComparison"
        )
        offer_component = next(
            component for component in components if component["component"] == "LoanOffer"
        )
        expected = sorted(
            set(loan_offer.allowed_terms_for(float(offer_component["amount"])))
            | {int(offer_component["months"])}
        )
        self.assertEqual([row["payoffMonths"] for row in scenario["scenarios"]], expected)
        for row in scenario["scenarios"]:
            self.assertGreater(row["monthlyPayment"], 0)
            self.assertGreater(row["totalInterest"], 0)
        highlighted = scenario["scenarios"][scenario["highlightIndex"]]
        self.assertIn("note", highlighted)

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
