"""M5 acceptance test: El Reves negotiation over HTTP.

Two persona rounds, take-control, and a simulated acceptance that emits a final
confirmed plan. Network-free via a dynamic scripted provider.
"""

import asyncio
import re
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
OFFER = {"principal": 127200.0, "apr": 0.24, "months": 60, "monthlyPayment": 3500.0}


def tool_call(name, arguments):
    return LLMResult(text="", tool_calls=(ToolCall(name=name, arguments=arguments),), usage=Usage(1, 1, 2), provider="scripted", model="scripted")


def text_result(text):
    return LLMResult(text=text, tool_calls=(), usage=Usage(1, 1, 2), provider="scripted", model="scripted")


def components(actor):
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
            "rounds": [{"round": 1, "actor": "bank"}],
        },
    ]


class DynamicProvider:
    """Advances through persona turns, extracting session_id from the prompt."""

    name = "scripted"
    model = "scripted"

    def __init__(self, actors):
        self._actors = list(actors)
        self._turn = -1
        self._step = 0

    @staticmethod
    def _session_id(messages):
        for message in messages:
            match = re.search(r"session_id:\s*(\S+)", message.content or "")
            if match:
                return match.group(1)
        return "unknown"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        if self._step == 0:
            self._turn += 1
            actor = self._actors[self._turn]
            session_id = self._session_id(messages)
            self._session_id_value = session_id
            self._actor = actor
            self._step = 1
            return tool_call(
                "record_negotiation_round",
                {"session_id": session_id, "actor": actor, "offer": {"monthlyPayment": 4100}},
            )
        if self._step == 1:
            self._step = 2
            return tool_call(
                "persist_ui",
                {
                    "user_id": "u_ana",
                    "domain": "loans_credits",
                    "catalog_id": CATALOG_ID,
                    "components": components(self._actor),
                    "data_model": {},
                },
            )
        self._step = 0
        return text_result("ok")


def _component_types(a2ui):
    comps = next(m for m in a2ui if "updateComponents" in m)["updateComponents"]["components"]
    return {c["component"] for c in comps}


class M5AcceptanceTest(unittest.TestCase):
    def test_negotiation_take_control_and_accept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "m5.sqlite3")

            async def prep() -> None:
                database = LocalSQLiteDatabase(db_path)
                await apply_schema(database)
                await seed(database)
                await database.close()

            asyncio.run(prep())

            provider = DynamicProvider(["bank", "advocate", "bank"])
            app = create_app(provider=provider, settings=Settings(database_path=db_path))

            with TestClient(app) as client:
                session_id = client.post("/api/session", json={"user_id": "u_ana"}).json()[
                    "session_id"
                ]

                bank = client.post(
                    f"/api/negotiation/{session_id}/turn", json={"user_id": "u_ana"}
                )
                self.assertEqual(bank.status_code, 200)
                self.assertEqual(bank.json()["actor"], "bank")
                self.assertIn("OfferCard", _component_types(bank.json()["a2ui"]))
                self.assertTrue(validate_messages(bank.json()["a2ui"]).ok)

                advocate = client.post(
                    f"/api/negotiation/{session_id}/turn", json={"user_id": "u_ana"}
                )
                self.assertEqual(advocate.json()["actor"], "advocate")
                self.assertEqual(advocate.json()["round"], 2)

                control = client.post(
                    f"/api/negotiation/{session_id}/take-control",
                    json={"user_id": "u_ana", "position": {"monthlyPayment": 3500}},
                )
                self.assertEqual(control.status_code, 200)
                self.assertEqual(control.json()["actor"], "bank")

                accept = client.post(
                    "/api/action",
                    json={
                        "surface_id": control.json()["surface_id"],
                        "name": "accept_offer",
                        "source_component_id": "offer",
                        "context": {"session_id": session_id, "offer": OFFER},
                    },
                )
                self.assertEqual(accept.status_code, 200)
                self.assertEqual(accept.json()["status"], "ok", accept.json())
                self.assertIn("PlanTable", _component_types(accept.json()["a2ui"]))

                final = client.get(f"/api/ui/{accept.json()['surface_id']}")
                self.assertEqual(final.status_code, 200)
                types = _component_types(final.json()["a2ui"])
                self.assertIn("PlanTable", types)
                self.assertNotIn("BreakAlert", types)
                data_model = next(
                    m for m in final.json()["a2ui"] if "updateDataModel" in m
                )["updateDataModel"]["value"]
                self.assertIsNone(data_model["plan"]["break"])

            async def count_rounds() -> int:
                database = LocalSQLiteDatabase(db_path)
                row = await database.fetch_one("SELECT COUNT(*) AS n FROM negotiation_rounds")
                await database.close()
                return row["n"]

            self.assertEqual(asyncio.run(count_rounds()), 4)


if __name__ == "__main__":
    unittest.main()
