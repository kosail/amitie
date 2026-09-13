import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agent.loan_detail import LoanDetailService
from agent.loans import _wants_private
from api.app import create_app
from config import Settings
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.finance import service as finance_service
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from providers.base import LLMResult, Usage
from providers.research import StaticPriceTableResearch, TopicResearch
from providers.voice import SynthesisResult

COMPONENTS = [
    {"id": "root", "component": "Column", "gap": 12, "children": ["h1", "offer"]},
    {"id": "h1", "component": "Heading", "level": 1, "text": "Tu crédito"},
    {
        "id": "offer",
        "component": "LoanOffer",
        "amount": {"path": "/loan/amount"},
        "apr": {"path": "/loan/apr"},
        "months": {"path": "/loan/termMonths"},
        "monthlyPayment": {"path": "/loan/monthlyPayment"},
        "totalInterest": {"path": "/loan/totalInterest"},
        "totalCost": {"path": "/loan/totalCost"},
        "cat": {"path": "/loan/cat"},
    },
]


class ScriptedProvider:
    name = "scripted"
    model = "scripted"

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        self.calls += 1
        return LLMResult(
            text=self._text, tool_calls=(), usage=Usage(1, 1, 2), provider="scripted", model="scripted"
        )


class CountingResearch:
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    async def research_topic(self, query, hints=None):
        self.calls += 1
        return TopicResearch(
            source=self.name,
            topic="viaje",
            items=[{"label": "Vuelo", "emoji": "✈️", "typical_mxn": 9000, "note": ""}],
            summary="",
        )


def _toolbox(database):
    return InProcessToolbox(
        {"finance": build_finance_server(database), "ui": build_ui_server(database)}
    )


class LoanListAndPurposeTest(unittest.TestCase):
    def test_create_loan_persists_purpose_and_lists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "loans.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with _toolbox(database) as toolbox:
                    created = await toolbox.call(
                        "create_loan",
                        {
                            "user_id": "u_ana",
                            "amount": 20000,
                            "term_months": 12,
                            "purpose": "estudiar",
                        },
                    )
                    self.assertEqual(created["status"], "ok")
                    loan_id = created["loan"]["id"]
                    self.assertEqual(created["loan"]["purpose"], "estudiar")

                    listed = await toolbox.call("list_loans", {"user_id": "u_ana"})
                    ids = [loan["id"] for loan in listed["loans"]]
                    self.assertIn(loan_id, ids)

                    fetched = await toolbox.call(
                        "get_loan", {"user_id": "u_ana", "loan_id": loan_id}
                    )
                    self.assertEqual(fetched["loan"]["purpose"], "estudiar")
                    self.assertFalse(fetched["loan"]["purposePrivate"])

                    context = await finance_service.loan_context(database, "u_ana", loan_id)
                    self.assertEqual(len(context["schedule"]), 12)
                    self.assertEqual(context["loan"]["id"], loan_id)

                await database.close()

            asyncio.run(run())

    def test_wants_private(self) -> None:
        self.assertTrue(_wants_private("prefiero no decirlo"))
        self.assertTrue(_wants_private("es un motivo privado"))
        self.assertFalse(_wants_private("es para un viaje"))


class LoanDetailServiceTest(unittest.TestCase):
    def _service(self, database, toolbox, text, research):
        provider = ScriptedProvider(json.dumps({"response_text": "Listo", "components": COMPONENTS}))
        return LoanDetailService(
            provider=provider, toolbox=toolbox, research=research, deadline_seconds=5.0
        )

    def test_detail_generates_once_then_reuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "detail.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with _toolbox(database) as toolbox:
                    created = await toolbox.call(
                        "create_loan",
                        {"user_id": "u_ana", "amount": 30000, "term_months": 24, "purpose": "viaje"},
                    )
                    loan_id = created["loan"]["id"]
                    research = CountingResearch()
                    service = self._service(database, toolbox, "", research)

                    first = await service.get_or_create(user_id="u_ana", entity="loan", entity_id=loan_id)
                    self.assertEqual(first["status"], "ok")
                    self.assertEqual(first["source"], "generated")
                    self.assertEqual(research.calls, 1)

                    second = await service.get_or_create(user_id="u_ana", entity="loan", entity_id=loan_id)
                    self.assertEqual(second["source"], "stored")
                    self.assertEqual(research.calls, 1)

                    rows = await database.fetch_all(
                        "SELECT id FROM generated_ui WHERE domain = 'loan_detail' AND entity_id = ?",
                        (loan_id,),
                    )
                    self.assertEqual(len(rows), 1)

                await database.close()

            asyncio.run(run())

    def test_private_purpose_skips_research(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "private.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with _toolbox(database) as toolbox:
                    created = await toolbox.call(
                        "create_loan",
                        {
                            "user_id": "u_ana",
                            "amount": 15000,
                            "term_months": 12,
                            "purpose": "privado",
                            "purpose_private": True,
                        },
                    )
                    loan_id = created["loan"]["id"]
                    research = CountingResearch()
                    service = self._service(database, toolbox, "", research)
                    result = await service.get_or_create(user_id="u_ana", entity="loan", entity_id=loan_id)
                    self.assertEqual(result["status"], "ok")
                    self.assertEqual(research.calls, 0)

                await database.close()

            asyncio.run(run())

    def test_unknown_loan_is_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "missing.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with _toolbox(database) as toolbox:
                    service = self._service(database, toolbox, "", CountingResearch())
                    result = await service.get_or_create(user_id="u_ana", entity="loan", entity_id="loan_nope")
                    self.assertEqual(result["status"], "not_found")

                await database.close()

            asyncio.run(run())


class StaticTopicResearchTest(unittest.TestCase):
    def test_static_topic_matches_category(self) -> None:
        provider = StaticPriceTableResearch()

        async def run() -> None:
            topic = await provider.research_topic("quiero estudiar una maestría")
            self.assertEqual(topic.topic, "estudios")
            self.assertTrue(topic.items)
            self.assertIn("emoji", topic.items[0])

        asyncio.run(run())


class FakeTTS:
    name = "fake"

    async def synthesize(self, text, voice_id="", speed=1.0):
        return SynthesisResult(b"MP3", "audio/mpeg", voice_id or "v", self.name)


class LoanDetailApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "api.sqlite3")

        async def prep() -> None:
            database = LocalSQLiteDatabase(Path(self.db_path))
            await apply_schema(database)
            await seed(database)
            await database.close()

        asyncio.run(prep())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _app(self):
        provider = ScriptedProvider(
            json.dumps({"response_text": "Listo", "components": COMPONENTS})
        )
        settings = Settings(
            database_path=self.db_path, audio_cache_dir=str(Path(self._tmp.name) / "audio")
        )
        return create_app(provider=provider, settings=settings, tts=FakeTTS())

    def test_list_and_detail_endpoints(self) -> None:
        with TestClient(self._app()) as client:
            created = client.post(
                "/api/loans",
                json={"user_id": "u_ana", "amount": 20000, "months": 12, "purpose": "viaje"},
            )
            self.assertEqual(created.status_code, 200, created.text)
            loan_id = created.json()["loan"]["id"]

            listed = client.get("/api/loans", params={"user_id": "u_ana"})
            self.assertEqual(listed.status_code, 200)
            items = listed.json()["items"]
            self.assertTrue(any(i["id"] == loan_id and i["source"] == "loan" for i in items))
            self.assertTrue(any(i["source"] == "liability" for i in items))

            detail = client.get(f"/api/loans/{loan_id}/ui", params={"user_id": "u_ana"})
            self.assertEqual(detail.status_code, 200, detail.text)
            body = detail.json()
            self.assertEqual(body["status"], "ok")
            self.assertTrue(body["surface_id"])
            self.assertTrue(any("updateComponents" in message for message in body["a2ui"]))

    def test_detail_unknown_loan_404(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/api/loans/loan_nope/ui", params={"user_id": "u_ana"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()


LOAN_SUMMARY = {
    "id": "summary",
    "component": "LoanSummary",
    "amount": {"path": "/loan/amount"},
    "months": {"path": "/loan/termMonths"},
    "monthlyPayment": {"path": "/loan/monthlyPayment"},
}

LIABILITY_SUMMARY = {
    "id": "summary",
    "component": "LiabilitySummary",
    "creditor": {"path": "/liability/creditor"},
    "balance": {"path": "/liability/balance"},
}


class CreditDetailGuardTest(unittest.TestCase):
    def _app_service(self, database, toolbox, payload):
        provider = ScriptedProvider(json.dumps(payload))
        return LoanDetailService(provider=provider, toolbox=toolbox, research=CountingResearch())

    def test_strips_offer_semantics_but_keeps_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "guard.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with _toolbox(database) as toolbox:
                    created = await toolbox.call(
                        "create_loan",
                        {"user_id": "u_ana", "amount": 20000, "term_months": 12, "purpose": "viaje"},
                    )
                    loan_id = created["loan"]["id"]
                    payload = {
                        "response_text": "ok",
                        "components": [
                            {"id": "root", "component": "Column", "children": ["summary", "offer", "btn"]},
                            LOAN_SUMMARY,
                            {
                                "id": "offer",
                                "component": "LoanOffer",
                                "amount": {"path": "/loan/amount"},
                                "apr": {"path": "/loan/apr"},
                                "months": {"path": "/loan/termMonths"},
                                "monthlyPayment": {"path": "/loan/monthlyPayment"},
                                "totalInterest": {"path": "/loan/totalInterest"},
                                "cat": {"path": "/loan/cat"},
                            },
                            {
                                "id": "btn",
                                "component": "Button",
                                "label": "Aceptar",
                                "action": {"event": {"name": "request_loan", "context": {}}},
                            },
                        ],
                    }
                    service = self._app_service(database, toolbox, payload)
                    result = await service.get_or_create(
                        user_id="u_ana", entity="loan", entity_id=loan_id
                    )
                    self.assertEqual(result["status"], "ok")

                    row = await database.fetch_one(
                        "SELECT template_json FROM generated_ui WHERE domain = 'loan_detail' AND entity_id = ?",
                        (loan_id,),
                    )
                    stored = json.loads(row["template_json"])
                    types = [c.get("component") for c in stored]
                    self.assertIn("LoanSummary", types)
                    self.assertNotIn("LoanOffer", types)
                    self.assertFalse(any("request_loan" in json.dumps(c) for c in stored))

                await database.close()

            asyncio.run(run())

    def test_liability_detail_has_abonar_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "liability.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with _toolbox(database) as toolbox:
                    listed = await toolbox.call("get_liabilities", {"user_id": "u_ana"})
                    self.assertTrue(listed["liabilities"])
                    liability_id = listed["liabilities"][0]["id"]
                    payload = {
                        "response_text": "ok",
                        "components": [
                            {"id": "root", "component": "Column", "children": ["summary"]},
                            LIABILITY_SUMMARY,
                        ],
                    }
                    service = self._app_service(database, toolbox, payload)
                    result = await service.get_or_create(
                        user_id="u_ana", entity="liability", entity_id=liability_id
                    )
                    self.assertEqual(result["status"], "ok")
                    self.assertEqual(result["source"], "generated")

                    row = await database.fetch_one(
                        "SELECT template_json FROM generated_ui WHERE domain = 'liability_detail' AND entity_id = ?",
                        (liability_id,),
                    )
                    stored = json.loads(row["template_json"])
                    self.assertTrue(any(c.get("component") == "LiabilitySummary" for c in stored))
                    self.assertTrue(any("abonar" in json.dumps(c) for c in stored))

                await database.close()

            asyncio.run(run())
