"""Golden-path acceptance: the full demo journey over HTTP, network-free.

Ordering per REQ-DEMO-01: intent -> MCP -> generated UI -> interaction ->
BreakAlert -> repair -> El Reves -> accepted outcome, plus Caja de Cristal and
the Kill Test. Asserts the journey completes well under the 90s budget.
"""

import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from config import Settings
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from providers.base import LLMResult, ToolCall, Usage
from ui_contract.validator import validate_messages

CATALOG_ID = "amitie.standard.v1"
OFFER = {"principal": 127200.0, "apr": 0.24, "months": 60, "monthlyPayment": 3500.0}

BREAK_COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["title", "plan", "alert"], "gap": 12},
    {"id": "title", "component": "Heading", "text": "Tu situacion"},
    {
        "id": "plan",
        "component": "PlanTable",
        "months": {"path": "/plan/months"},
        "breakMonth": {"path": "/plan/breakMonth"},
    },
    {
        "id": "alert",
        "component": "BreakAlert",
        "month": {"path": "/plan/break/month"},
        "shortfall": {"path": "/plan/break/shortfall"},
    },
]

FIXED_COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["title", "plan"], "gap": 12},
    {"id": "title", "component": "Heading", "text": "Tu situacion"},
    {
        "id": "plan",
        "component": "PlanTable",
        "months": {"path": "/plan/months"},
        "breakMonth": {"path": "/plan/breakMonth"},
    },
]


def negotiation_components(actor):
    return [
        {"id": "root", "component": "Column", "children": ["offer", "transcript"], "gap": 12},
        {
            "id": "offer",
            "component": "OfferCard",
            "actor": actor,
            "headline": "Oferta",
            "terms": {"apr": 0.24, "months": 48, "monthlyPayment": 4100, "totalCost": 196800},
        },
        {
            "id": "transcript",
            "component": "NegotiationTranscript",
            "rounds": [{"round": 1, "actor": actor}],
        },
    ]


def tool_call(name, arguments):
    return LLMResult(text="", tool_calls=(ToolCall(name=name, arguments=arguments),), usage=Usage(1, 1, 2), provider="scripted", model="scripted")


def text_result(text):
    return LLMResult(text=text, tool_calls=(), usage=Usage(1, 1, 2), provider="scripted", model="scripted")


def persist(components, simulation=None):
    args = {
        "user_id": "u_ana",
        "domain": "loans_credits",
        "catalog_id": CATALOG_ID,
        "components": components,
        "data_model": {},
    }
    if simulation is not None:
        args["simulation"] = simulation
    return tool_call("persist_ui", args)


class QueueProvider:
    name = "scripted"
    model = "scripted"

    def __init__(self):
        self._queue = []
        self.calls = 0

    def push(self, *results):
        self._queue.extend(results)

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        self.calls += 1
        if self._queue:
            return self._queue.pop(0)
        return text_result("(sin guion)")


def _types(a2ui):
    return {c["component"] for m in a2ui if "updateComponents" in m for c in m["updateComponents"]["components"]}


def _ids(a2ui):
    return {c["id"] for m in a2ui if "updateComponents" in m for c in m["updateComponents"]["components"]}


class GoldenPathTest(unittest.TestCase):
    def test_full_journey(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "golden.sqlite3")

            async def prep():
                database = LocalSQLiteDatabase(db_path)
                await apply_schema(database)
                await seed(database)
                await database.close()

            asyncio.run(prep())

            provider = QueueProvider()
            app = create_app(provider=provider, settings=Settings(database_path=db_path))
            started = time.perf_counter()

            with TestClient(app) as client:
                session_id = client.post("/api/session", json={"user_id": "u_ana"}).json()["session_id"]

                # 1. Intent -> MCP retrieval -> generated UI with BreakAlert (mutation #1).
                provider.push(
                    tool_call("get_financial_context", {"user_id": "u_ana"}),
                    tool_call("simulate_plan", {"user_id": "u_ana", "strategy": "avalanche"}),
                    tool_call("detect_plan_breaks", {"user_id": "u_ana", "strategy": "avalanche"}),
                    persist(BREAK_COMPONENTS, {"strategy": "avalanche"}),
                    text_result("Encontré un problema."),
                )
                message = client.post(
                    "/api/message", json={"session_id": session_id, "text": "Tengo 5 deudas y ya no puedo"}
                ).json()
                self.assertEqual(message["status"], "ok", message)
                debt_surface = message["surface_id"]

                hydrated = client.get(f"/api/ui/{debt_surface}").json()
                self.assertIn("BreakAlert", _types(hydrated["a2ui"]))
                self.assertIn("assumptions-section", _ids(hydrated["a2ui"]))
                self.assertIn("assumption-extra_income", _ids(hydrated["a2ui"]))

                # 2. Interaction -> repair/reflow (mutation #2).
                provider.push(
                    tool_call("simulate_plan", {"user_id": "u_ana", "strategy": "avalanche", "extra_income": 8000}),
                    tool_call("detect_plan_breaks", {"user_id": "u_ana", "strategy": "avalanche", "extra_income": 8000}),
                    persist(FIXED_COMPONENTS, {"strategy": "avalanche", "extra_income": 8000}),
                    text_result("Plan corregido."),
                )
                repaired = client.post(
                    "/api/action",
                    json={
                        "surface_id": debt_surface,
                        "name": "approve_plan",
                        "source_component_id": "plan",
                        "context": {"extra_income": 8000},
                    },
                ).json()
                self.assertEqual(repaired["status"], "ok", repaired)
                fixed = client.get(f"/api/ui/{repaired['surface_id']}").json()
                self.assertNotIn("BreakAlert", _types(fixed["a2ui"]))

                # 3. El Reves negotiation (two rounds).
                provider.push(
                    tool_call("record_negotiation_round", {"session_id": session_id, "actor": "bank", "offer": {"monthlyPayment": 4100}}),
                    persist(negotiation_components("bank")),
                    text_result("ok"),
                )
                bank = client.post(f"/api/negotiation/{session_id}/turn", json={"user_id": "u_ana"}).json()
                self.assertEqual(bank["actor"], "bank")
                self.assertIn("OfferCard", _types(bank["a2ui"]))

                provider.push(
                    tool_call("record_negotiation_round", {"session_id": session_id, "actor": "advocate", "offer": {"monthlyPayment": 3500}}),
                    persist(negotiation_components("advocate")),
                    text_result("ok"),
                )
                advocate = client.post(f"/api/negotiation/{session_id}/turn", json={"user_id": "u_ana"}).json()
                self.assertEqual(advocate["actor"], "advocate")

                # 4. Accepted outcome.
                accept = client.post(
                    "/api/action",
                    json={
                        "surface_id": advocate["surface_id"],
                        "name": "accept_offer",
                        "source_component_id": "offer",
                        "context": {"session_id": session_id, "offer": OFFER},
                    },
                ).json()
                self.assertEqual(accept["status"], "ok", accept)
                self.assertIn("PlanTable", _types(accept["a2ui"]))
                accepted_surface = accept["surface_id"]

                # 5. Caja de Cristal: edit an assumption -> agent rebuilds.
                provider.push(
                    tool_call("simulate_plan", {"user_id": "u_ana", "strategy": "avalanche", "extra_income": 8000}),
                    tool_call("detect_plan_breaks", {"user_id": "u_ana", "strategy": "avalanche", "extra_income": 8000}),
                    persist(FIXED_COMPONENTS, {"strategy": "avalanche", "extra_income": 8000}),
                    text_result("Recalculé con tu suposición."),
                )
                rebuilt = client.post(
                    "/api/action",
                    json={
                        "surface_id": accepted_surface,
                        "name": "toggle_assumption",
                        "source_component_id": "assumption-extra_income",
                        "context": {"key": "extra_income", "value": 8000},
                    },
                ).json()
                self.assertEqual(rebuilt["status"], "ok", rebuilt)

                # 6. Kill Test: frozen artifact, no agent involvement.
                before = provider.calls
                kill = client.get(f"/debug/kill-test/{rebuilt['surface_id']}")
                self.assertEqual(kill.status_code, 200, kill.text)
                self.assertTrue(kill.json()["a2ui"])
                self.assertEqual(provider.calls, before, "Kill Test must not call the LLM")
                self.assertTrue(validate_messages(kill.json()["a2ui"]).ok)

                self.assertLess(time.perf_counter() - started, 90.0)


if __name__ == "__main__":
    unittest.main()
