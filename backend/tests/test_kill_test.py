import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server


def _components(a2ui):
    return next(m for m in a2ui if "updateComponents" in m)["updateComponents"]["components"]


def _types(a2ui):
    return {c["component"] for c in _components(a2ui)}


def _data_model(a2ui):
    return next(m for m in a2ui if "updateDataModel" in m)["updateDataModel"]["value"]


class KillTestTest(unittest.TestCase):
    def test_frozen_artifact_survives_live_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "kt.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with InProcessToolbox({"ui": build_ui_server(database)}) as toolbox:
                    persisted = await toolbox.call(
                        "persist_ui",
                        {
                            "user_id": "u_ana",
                            "domain": "loans_credits",
                            "catalog_id": "amitie.standard.v1",
                            "components": [
                                {"id": "root", "component": "Column", "children": ["plan"], "gap": 12},
                                {
                                    "id": "plan",
                                    "component": "PlanTable",
                                    "months": {"path": "/plan/months"},
                                    "breakMonth": {"path": "/plan/breakMonth"},
                                },
                            ],
                            "data_model": {},
                            "simulation": {"strategy": "avalanche"},
                        },
                    )
                    surface = persisted["surface_id"]

                    frozen = await toolbox.call("kill_test", {"surface_id": surface})
                    self.assertEqual(frozen["status"], "ok", frozen)
                    self.assertIn("BreakAlert", _types(frozen["a2ui"]))
                    self.assertEqual(_data_model(frozen["a2ui"])["plan"]["break"]["month"], 1)

                    # Change reality so the live plan no longer breaks.
                    await database.execute(
                        "UPDATE users SET monthly_income = 40000 WHERE id = 'u_ana'"
                    )
                    live = await toolbox.call("hydrate_ui", {"surface_id": surface})
                    self.assertNotIn("BreakAlert", _types(live["a2ui"]))

                    # The Kill Test is unmoved: genuine frozen artifact (INV-032).
                    again = await toolbox.call("kill_test", {"surface_id": surface})
                    self.assertIn("BreakAlert", _types(again["a2ui"]))
                    self.assertEqual(again, frozen)

                    missing = await toolbox.call("kill_test", {"surface_id": "nope"})
                    self.assertEqual(missing["status"], "error")

                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
