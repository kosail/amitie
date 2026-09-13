import asyncio
import tempfile
import unittest
from pathlib import Path

from agent.negotiation import NegotiationService
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from providers.base import LLMResult, ToolCall, Usage
from ui_contract.validator import validate_messages

CATALOG_ID = "amitie.standard.v1"
SESSION_ID = "sess_neg"
NOW = "2026-09-12T12:00:00Z"


class ScriptedProvider:
    name = "scripted"
    model = "scripted"

    def __init__(self, results):
        self._results = list(results)

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        if not self._results:
            return text_result("(sin guion)")
        return self._results.pop(0)


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


def persona_script(actor):
    return [
        tool_call("record_negotiation_round", {"session_id": SESSION_ID, "actor": actor, "offer": {"monthlyPayment": 4100}}),
        tool_call("persist_ui", {"user_id": "u_ana", "domain": "loans_credits", "catalog_id": CATALOG_ID, "components": components(actor), "data_model": {}}),
        text_result("ok"),
    ]


def _component_types(a2ui):
    comps = next(m for m in a2ui if "updateComponents" in m)["updateComponents"]["components"]
    return {c["component"] for c in comps}


class NegotiationServiceTest(unittest.TestCase):
    def test_two_rounds_and_take_control(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "neg.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                await database.execute(
                    "INSERT INTO sessions (id, user_id, active_surface_id, context_json, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (SESSION_ID, "u_ana", None, "{}", NOW, NOW),
                )
                servers = {"finance": build_finance_server(database), "ui": build_ui_server(database)}

                async with InProcessToolbox(servers) as toolbox:
                    provider = ScriptedProvider(
                        persona_script("bank") + persona_script("advocate") + persona_script("bank")
                    )
                    service = NegotiationService(provider=provider, toolbox=toolbox)

                    bank = await service.run_round(session_id=SESSION_ID, user_id="u_ana")
                    self.assertEqual(bank["status"], "ok", bank)
                    self.assertEqual(bank["actor"], "bank")
                    self.assertEqual(bank["round"], 1)
                    self.assertIn("OfferCard", _component_types(bank["a2ui"]))
                    self.assertTrue(validate_messages(bank["a2ui"]).ok)

                    advocate = await service.run_round(session_id=SESSION_ID, user_id="u_ana")
                    self.assertEqual(advocate["actor"], "advocate")
                    self.assertEqual(advocate["round"], 2)

                    control = await service.run_round(
                        session_id=SESSION_ID,
                        user_id="u_ana",
                        position={"monthlyPayment": 3500},
                        take_control=True,
                    )
                    self.assertEqual(control["status"], "ok", control)
                    self.assertEqual(control["actor"], "bank")

                count = await database.fetch_one("SELECT COUNT(*) AS n FROM negotiation_rounds")
                self.assertEqual(count["n"], 4)  # bank, advocate, user, bank
                session = await database.fetch_one(
                    "SELECT context_json FROM sessions WHERE id = ?", (SESSION_ID,)
                )
                self.assertIn("take_control", session["context_json"])
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
