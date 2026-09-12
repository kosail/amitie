"""M3 acceptance test: the La Mesa debt-intent slice, end to end over HTTP.

One debt sentence -> agent reads finance through MCP -> emits a DebtNode
constellation + TradeoffScale -> user action -> agent regenerates. Network-free
via a scripted provider; payloads validated against the A2UI SDK schemas.
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

COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["title", "debt", "scale"], "gap": 16},
    {"id": "title", "component": "Heading", "text": "Tu situacion actual", "level": 1},
    {
        "id": "debt",
        "component": "DebtNode",
        "creditor": "BBVA",
        "balance": {"path": "/liabilities/0/balance"},
        "apr": {"path": "/liabilities/0/apr"},
        "minPayment": {"path": "/liabilities/0/minPayment"},
    },
    {
        "id": "scale",
        "component": "TradeoffScale",
        "leftLabel": "Bajar mi pago mensual",
        "rightLabel": "Pagar menos intereses",
        "value": {"path": "/ui/strategyTilt"},
        "action": {"event": {"name": "tune_tradeoff", "context": {"value": "/ui/strategyTilt"}}},
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


def persist_call() -> LLMResult:
    return tool_call(
        "persist_ui",
        {
            "user_id": "u_ana",
            "domain": "loans_credits",
            "catalog_id": CATALOG_ID,
            "components": COMPONENTS,
            "data_model": {},
        },
    )


class ScriptedProvider:
    name = "scripted"
    model = "scripted"

    def __init__(self, results: list[LLMResult]) -> None:
        self._results = list(results)

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        if not self._results:
            return text_result("(sin guion)")
        return self._results.pop(0)


class M3AcceptanceTest(unittest.TestCase):
    def test_debt_intent_slice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "acceptance.sqlite3")

            async def prep() -> None:
                database = LocalSQLiteDatabase(db_path)
                await apply_schema(database)
                await seed(database)
                await database.close()

            asyncio.run(prep())

            provider = ScriptedProvider(
                [
                    tool_call("get_financial_context", {"user_id": "u_ana"}),
                    persist_call(),
                    text_result("Aqui esta tu diagnostico."),
                    persist_call(),
                    text_result("Plan actualizado."),
                ]
            )
            app = create_app(provider=provider, settings=Settings(database_path=db_path))

            with TestClient(app) as client:
                # 1. Session
                session_id = client.post("/api/session", json={"user_id": "u_ana"}).json()[
                    "session_id"
                ]

                # 2. Debt sentence -> generated surface
                message = client.post(
                    "/api/message",
                    json={"session_id": session_id, "text": "Tengo 5 deudas y ya no puedo"},
                )
                self.assertEqual(message.status_code, 200)
                body = message.json()
                self.assertEqual(body["status"], "ok", body)
                self.assertTrue(body["surface_id"].startswith("surf_"))

                # 3. The interface is valid A2UI (jsonschema + semantics)
                validation = validate_messages(body["a2ui"])
                self.assertTrue(validation.ok, validation.issues)

                components = next(
                    m for m in body["a2ui"] if "updateComponents" in m
                )["updateComponents"]["components"]
                types = {c["component"] for c in components}
                self.assertIn("DebtNode", types)
                self.assertIn("TradeoffScale", types)
                debt = next(c for c in components if c["component"] == "DebtNode")
                self.assertEqual(debt["balance"], {"path": "/liabilities/0/balance"})

                # 4. Hydration returns fresh, real data
                surface_id = body["surface_id"]
                hydrated = client.get(f"/api/ui/{surface_id}")
                self.assertEqual(hydrated.status_code, 200)
                data_model = next(
                    m for m in hydrated.json()["a2ui"] if "updateDataModel" in m
                )["updateDataModel"]["value"]
                self.assertEqual(data_model["totals"]["debt"], 127200.0)

                # 5. User interaction -> agent regenerates
                action = client.post(
                    "/api/action",
                    json={
                        "surface_id": surface_id,
                        "name": "tune_tradeoff",
                        "source_component_id": "scale",
                        "context": {"value": 60},
                    },
                )
                self.assertEqual(action.status_code, 200)
                self.assertEqual(action.json()["status"], "ok", action.json())
                self.assertTrue(validate_messages(action.json()["a2ui"]).ok)

                # 6. The interaction was recorded and the turn was traced
                trace_id = message.headers["x-trace-id"]
                trace = client.get(f"/debug/trace/{trace_id}")
                self.assertEqual(trace.status_code, 200)
                self.assertTrue(trace.json()["events"])


if __name__ == "__main__":
    unittest.main()
