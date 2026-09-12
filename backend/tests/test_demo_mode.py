import asyncio
import tempfile
import unittest
from pathlib import Path

from agent.service import AgentService
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from providers.base import ProviderUnavailableError

SURFACE = [
    {"id": "root", "component": "Column", "children": ["t"], "gap": 12},
    {"id": "t", "component": "Heading", "text": "Tu plan"},
]


class FailingProvider:
    name = "failing"
    model = "failing"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        raise ProviderUnavailableError("provider down")


class DemoModeTest(unittest.TestCase):
    def test_serves_last_surface_on_provider_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "demo.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                toolbox = InProcessToolbox(
                    {"finance": build_finance_server(database), "ui": build_ui_server(database)}
                )
                await toolbox.__aenter__()
                try:
                    persisted = await toolbox.call(
                        "persist_ui",
                        {
                            "user_id": "u_ana",
                            "domain": "loans_credits",
                            "catalog_id": "amitie.standard.v1",
                            "components": SURFACE,
                            "data_model": {},
                        },
                    )
                    await database.execute(
                        "INSERT INTO sessions (id, user_id, active_surface_id, context_json, "
                        "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                        ("s_demo", "u_ana", persisted["surface_id"], "{}", "t", "t"),
                    )

                    cached = AgentService(
                        provider=FailingProvider(), toolbox=toolbox, demo_mode=True
                    )
                    result = await cached.run_turn(session_id="s_demo", user_id="u_ana", text="hola")
                    self.assertEqual(result["status"], "ok", result)
                    self.assertEqual(result["surface_id"], persisted["surface_id"])
                    self.assertTrue(result["a2ui"])

                    strict = AgentService(
                        provider=FailingProvider(), toolbox=toolbox, demo_mode=False
                    )
                    errored = await strict.run_turn(session_id="s_demo", user_id="u_ana", text="hola")
                    self.assertEqual(errored["status"], "error")
                finally:
                    await toolbox.__aexit__(None, None, None)
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
