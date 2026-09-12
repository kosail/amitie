import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from ui_contract.validator import validate_messages

CATALOG_ID = "amitie.standard.v1"

COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["title"], "gap": 8},
    {"id": "title", "component": "Heading", "text": "Tu situacion"},
]


def _component_types(a2ui: list) -> set[str]:
    components = next(m for m in a2ui if "updateComponents" in m)["updateComponents"]["components"]
    return {component["component"] for component in components}


def _persist_args(simulation: dict) -> dict:
    return {
        "user_id": "u_ana",
        "domain": "loans_credits",
        "catalog_id": CATALOG_ID,
        "components": COMPONENTS,
        "data_model": {},
        "simulation": simulation,
    }


class RevalidationTest(unittest.TestCase):
    def test_break_alert_inserted_then_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "revalidate.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_ui_server(database)

                async with InProcessToolbox({"ui": server}) as toolbox:
                    breaking = await toolbox.call(
                        "persist_ui", _persist_args({"strategy": "avalanche"})
                    )
                    surface_id = breaking["surface_id"]

                    first = await toolbox.call("hydrate_ui", {"surface_id": surface_id})
                    self.assertEqual(first["version"], 2)
                    types = _component_types(first["a2ui"])
                    self.assertIn("BreakAlert", types)
                    self.assertIn("PlanTable", types)
                    self.assertTrue(validate_messages(first["a2ui"]).ok, validate_messages(first["a2ui"]).issues)
                    data_model = next(
                        m for m in first["a2ui"] if "updateDataModel" in m
                    )["updateDataModel"]["value"]
                    self.assertEqual(data_model["plan"]["break"]["month"], 1)

                    second = await toolbox.call("hydrate_ui", {"surface_id": surface_id})
                    self.assertEqual(second["version"], 2)  # idempotent
                    self.assertIn("BreakAlert", _component_types(second["a2ui"]))

                    repaired = await toolbox.call(
                        "persist_ui",
                        _persist_args({"strategy": "avalanche", "extra_income": 8000}),
                    )
                    fixed = await toolbox.call(
                        "hydrate_ui", {"surface_id": repaired["surface_id"]}
                    )
                    self.assertNotIn("BreakAlert", _component_types(fixed["a2ui"]))
                    self.assertIn("PlanTable", _component_types(fixed["a2ui"]))
                    self.assertTrue(validate_messages(fixed["a2ui"]).ok, validate_messages(fixed["a2ui"]).issues)

                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
