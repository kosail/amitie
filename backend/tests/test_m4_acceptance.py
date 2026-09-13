"""M4 acceptance test: BreakAlert mutation and repair over HTTP.

The agent discovers a broken plan and proactively emits a BreakAlert surface
(Mutation #1); after a repair action it re-simulates and re-emits the plan
without the alert (Mutation #2). Network-free via a scripted provider.
"""

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
from providers.base import LLMResult, ToolCall, Usage
from ui_contract.validator import validate_messages

CATALOG_ID = "amitie.standard.v1"

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


def tool_call(name: str, arguments: dict) -> LLMResult:
    return LLMResult(
        text="",
        tool_calls=(ToolCall(name=name, arguments=arguments),),
        usage=Usage(1, 1, 2),
        provider="scripted",
        model="scripted",
    )


def text_result(text: str) -> LLMResult:
    return LLMResult(
        text=text, tool_calls=(), usage=Usage(1, 1, 2), provider="scripted", model="scripted"
    )


def persist_call(components: list, simulation: dict) -> LLMResult:
    return tool_call(
        "persist_ui",
        {
            "user_id": "u_ana",
            "domain": "loans_credits",
            "catalog_id": CATALOG_ID,
            "components": components,
            "data_model": {},
            "simulation": simulation,
        },
    )


class ScriptedProvider:
    name = "scripted"
    model = "scripted"

    def __init__(self, results: list[LLMResult]) -> None:
        self._results = list(results)

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        if not self._results:
            return text_result("(sin guion)")
        return self._results.pop(0)


def _component_types(a2ui: list) -> set[str]:
    components = next(m for m in a2ui if "updateComponents" in m)["updateComponents"]["components"]
    return {component["component"] for component in components}


class M4AcceptanceTest(unittest.TestCase):
    def test_break_alert_and_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "m4.sqlite3")

            async def prep() -> None:
                database = LocalSQLiteDatabase(db_path)
                await apply_schema(database)
                await seed(database)
                await database.close()

            asyncio.run(prep())

            provider = ScriptedProvider(
                [
                    tool_call("get_financial_context", {"user_id": "u_ana"}),
                    tool_call("simulate_plan", {"user_id": "u_ana", "strategy": "avalanche"}),
                    tool_call("detect_plan_breaks", {"user_id": "u_ana", "strategy": "avalanche"}),
                    persist_call(BREAK_COMPONENTS, {"strategy": "avalanche"}),
                    text_result("Encontre un problema en tu plan."),
                    tool_call(
                        "simulate_plan",
                        {"user_id": "u_ana", "strategy": "avalanche", "extra_income": 8000},
                    ),
                    tool_call(
                        "detect_plan_breaks",
                        {"user_id": "u_ana", "strategy": "avalanche", "extra_income": 8000},
                    ),
                    persist_call(
                        FIXED_COMPONENTS,
                        {"strategy": "avalanche", "extra_income": 8000},
                    ),
                    text_result("Plan corregido."),
                ]
            )
            app = create_app(provider=provider, settings=Settings(database_path=db_path))

            with TestClient(app) as client:
                session_id = client.post("/api/session", json={"user_id": "u_ana"}).json()[
                    "session_id"
                ]

                # Mutation #1: the agent discovers the break and emits BreakAlert.
                message = client.post(
                    "/api/message",
                    json={"session_id": session_id, "text": "Tengo 5 deudas y ya no puedo"},
                )
                body = message.json()
                self.assertEqual(body["status"], "ok", body)
                self.assertIn("BreakAlert", _component_types(body["a2ui"]))
                self.assertIn("PlanTable", _component_types(body["a2ui"]))
                self.assertTrue(validate_messages(body["a2ui"]).ok)

                # Re-fetch revalidates structurally and keeps the alert.
                surface_id = body["surface_id"]
                hydrated = client.get(f"/api/ui/{surface_id}")
                self.assertIn("BreakAlert", _component_types(hydrated.json()["a2ui"]))
                data_model = next(
                    m for m in hydrated.json()["a2ui"] if "updateDataModel" in m
                )["updateDataModel"]["value"]
                self.assertEqual(data_model["plan"]["break"]["month"], 1)

                # Mutation #2: repair action -> re-simulate -> alert removed.
                action = client.post(
                    "/api/action",
                    json={
                        "surface_id": surface_id,
                        "name": "approve_plan",
                        "source_component_id": "plan",
                        "context": {"extra_income": 8000},
                    },
                )
                self.assertEqual(action.status_code, 200)
                self.assertEqual(action.json()["status"], "ok", action.json())
                types = _component_types(action.json()["a2ui"])
                self.assertNotIn("BreakAlert", types)
                self.assertIn("PlanTable", types)
                self.assertTrue(validate_messages(action.json()["a2ui"]).ok)


if __name__ == "__main__":
    unittest.main()
