"""M6 acceptance test: Saving Bags over HTTP.

A vague goal becomes a question form, then a researched, dated, funded plan
(with a loan handoff when it does not reach). Network-free: research uses the
deterministic static table and the LLM is a scripted provider.
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

FORM_COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["title", "days", "style"], "gap": 12},
    {"id": "title", "component": "Heading", "text": "Cuéntame de tu viaje", "level": 2},
    {
        "id": "days",
        "component": "TextField",
        "label": "¿Cuántos días?",
        "action": {"event": {"name": "adjust_goal", "context": {}}},
    },
    {
        "id": "style",
        "component": "ChoiceGroup",
        "options": [
            {"value": "mochilero", "label": "Mochilero"},
            {"value": "confort", "label": "Confort"},
        ],
        "action": {"event": {"name": "select_strategy", "context": {}}},
    },
]


def plan_components() -> list:
    return [
        {
            "id": "root",
            "component": "Column",
            "children": ["title", "loan"],
            "gap": 12,
        },
        {"id": "title", "component": "Heading", "text": "Tu plan de ahorro", "level": 1},
        {
            "id": "loan",
            "component": "OfferCard",
            "actor": "bank",
            "headline": "Préstamo para completar tu meta",
            "terms": {"apr": 0.24, "months": 24, "monthlyPayment": 2000, "totalCost": 48000},
            "action": {"event": {"name": "accept_offer", "context": {}}},
        },
    ]


def tool_call(name, arguments):
    return LLMResult(
        text="",
        tool_calls=(ToolCall(name=name, arguments=arguments),),
        usage=Usage(1, 1, 2),
        provider="scripted",
        model="scripted",
    )


def text_result(text):
    return LLMResult(
        text=text, tool_calls=(), usage=Usage(1, 1, 2), provider="scripted", model="scripted"
    )


def persist(components, entity_id=""):
    return tool_call(
        "persist_ui",
        {
            "user_id": "u_ana",
            "domain": "saving_bag",
            "catalog_id": CATALOG_ID,
            "components": components,
            "data_model": {},
            "entity_id": entity_id,
        },
    )


class QueueProvider:
    name = "scripted"
    model = "scripted"

    def __init__(self) -> None:
        self._queue: list[LLMResult] = []

    def push(self, *results: LLMResult) -> None:
        self._queue.extend(results)

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        if self._queue:
            return self._queue.pop(0)
        return text_result("(sin guion)")


def _components(a2ui):
    return next(m for m in a2ui if "updateComponents" in m)["updateComponents"]["components"]


def _types(a2ui):
    return {c["component"] for c in _components(a2ui)}


def _ids(a2ui):
    return {c["id"] for c in _components(a2ui)}


class M6AcceptanceTest(unittest.TestCase):
    def test_saving_bag_full_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "m6.sqlite3")

            async def prep() -> None:
                database = LocalSQLiteDatabase(db_path)
                await apply_schema(database)
                await seed(database)
                await database.close()

            asyncio.run(prep())

            provider = QueueProvider()
            app = create_app(provider=provider, settings=Settings(database_path=db_path))

            with TestClient(app) as client:
                session_id = client.post("/api/session", json={"user_id": "u_ana"}).json()[
                    "session_id"
                ]

                # 1. Vague goal -> agent emits an inferred question form.
                provider.push(persist(FORM_COMPONENTS), text_result("Cuéntame de tu viaje."))
                created = client.post(
                    "/api/saving-bags",
                    json={
                        "user_id": "u_ana",
                        "name": "Viaje a Japón",
                        "target_amount": 45000.0,
                        "target_date": "2027-04-01",
                        "session_id": session_id,
                    },
                )
                self.assertEqual(created.status_code, 200, created.json())
                body = created.json()
                self.assertEqual(body["status"], "ok", body)
                bag_id = body["bag_id"]
                self.assertIn("TextField", _types(body["a2ui"]))
                self.assertTrue(validate_messages(body["a2ui"]).ok)

                # 2. Answers -> research, estimate, feasibility, plan surface.
                provider.push(
                    tool_call("research_costs", {"bag_id": bag_id}),
                    tool_call("estimate_total", {"bag_id": bag_id}),
                    tool_call("compute_feasibility", {"bag_id": bag_id}),
                    persist(plan_components(), entity_id=bag_id),
                    text_result("Investigué costos reales y armé tu plan."),
                )
                answered = client.post(
                    f"/api/saving-bags/{bag_id}/answer",
                    json={
                        "user_id": "u_ana",
                        "session_id": session_id,
                        "answers": [
                            {"question_key": "days", "answer": "10"},
                            {"question_key": "travelers", "answer": "2"},
                            {"question_key": "style", "answer": "mochilero"},
                        ],
                    },
                )
                self.assertEqual(answered.status_code, 200, answered.json())
                self.assertEqual(answered.json()["status"], "ok", answered.json())

                # 3. Re-fetch hydrates and structurally revalidates the saved surface.
                fetched = client.get(f"/api/saving-bags/{bag_id}")
                self.assertEqual(fetched.status_code, 200)
                data = fetched.json()
                self.assertEqual(data["status"], "ok", data)
                self.assertEqual(data["plan"]["feasibility"], "off_track")
                self.assertTrue(data["plan"]["redirect"]["recommended"])
                types = _types(data["a2ui"])
                for expected in (
                    "GoalJar",
                    "ProgressBar",
                    "CashFlowTimeline",
                    "OfferCard",
                ):
                    self.assertIn(expected, types)
                ids = _ids(data["a2ui"])
                self.assertIn("savings-section", ids)
                self.assertIn("savings-alert", ids)
                self.assertTrue(validate_messages(data["a2ui"]).ok, validate_messages(data["a2ui"]).issues)

                # 4. Refresh reruns research and recomputes the plan.
                provider.push(
                    persist(plan_components(), entity_id=bag_id),
                    text_result("Actualicé los costos de tu viaje."),
                )
                refreshed = client.post(
                    f"/api/saving-bags/{bag_id}/refresh",
                    json={"user_id": "u_ana", "session_id": session_id},
                )
                self.assertEqual(refreshed.status_code, 200, refreshed.json())
                self.assertEqual(refreshed.json()["status"], "ok", refreshed.json())

                listed = client.get("/api/saving-bags", params={"user_id": "u_ana"})
                self.assertIn(bag_id, [bag["id"] for bag in listed.json()["bags"]])

            async def counts():
                database = LocalSQLiteDatabase(db_path)
                research = await database.fetch_one(
                    "SELECT COUNT(*) AS n FROM saving_bag_research WHERE bag_id = ?", (bag_id,)
                )
                plan = await database.fetch_one(
                    "SELECT COUNT(*) AS n FROM saving_bag_plan WHERE bag_id = ?", (bag_id,)
                )
                await database.close()
                return research["n"], plan["n"]

            research_count, plan_count = asyncio.run(counts())
            self.assertEqual(research_count, 2)
            self.assertEqual(plan_count, 1)


if __name__ == "__main__":
    unittest.main()
