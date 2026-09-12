import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server

CATALOG_ID = "amitie.standard.v1"

COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["title", "debt"], "gap": 8},
    {"id": "title", "component": "Heading", "text": "Deuda total: {{totals.debt}}"},
    {
        "id": "debt",
        "component": "DebtNode",
        "creditor": "BBVA",
        "balance": {"path": "/liabilities/0/balance"},
        "apr": {"path": "/liabilities/0/apr"},
        "minPayment": {"path": "/liabilities/0/minPayment"},
    },
]

DATA_MODEL = {
    "totals": {"debt": 127200.0},
    "liabilities": [{"balance": 48000.0, "apr": 0.54, "minPayment": 2900.0}],
}


class UiToolsTest(unittest.TestCase):
    def test_persist_hydrate_and_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "ui.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_ui_server(database)

                async with InProcessToolbox({"ui": server}) as toolbox:
                    persisted = await toolbox.call(
                        "persist_ui",
                        {
                            "user_id": "u_ana",
                            "domain": "loans_credits",
                            "catalog_id": CATALOG_ID,
                            "components": COMPONENTS,
                            "data_model": DATA_MODEL,
                        },
                    )
                    self.assertEqual(persisted["status"], "ok")
                    surface_id = persisted["surface_id"]
                    self.assertTrue(any("createSurface" in message for message in persisted["a2ui"]))

                    rejected = await toolbox.call(
                        "persist_ui",
                        {
                            "user_id": "u_ana",
                            "domain": "loans_credits",
                            "catalog_id": CATALOG_ID,
                            "components": [{"id": "x", "component": {"Bogus": {}}}],
                            "data_model": {},
                        },
                    )
                    self.assertEqual(rejected["status"], "error")
                    self.assertTrue(rejected["issues"])

                    hydrated = await toolbox.call("hydrate_ui", {"surface_id": surface_id})
                    self.assertEqual(hydrated["status"], "ok")
                    data_message = next(m for m in hydrated["a2ui"] if "updateDataModel" in m)
                    self.assertEqual(data_message["updateDataModel"]["value"]["totals"]["debt"], 127200.0)
                    components = next(m for m in hydrated["a2ui"] if "updateComponents" in m)[
                        "updateComponents"
                    ]["components"]
                    heading = next(c for c in components if c["id"] == "title")
                    self.assertEqual(heading["text"], "Deuda total: 127200.0")

                    action = await toolbox.call(
                        "a2ui_action",
                        {
                            "user_id": "u_ana",
                            "surface_id": surface_id,
                            "name": "tune_tradeoff",
                            "source_component_id": "strategy",
                            "context": {"value": 60},
                        },
                    )
                    self.assertEqual(action["status"], "ok")

                count = await database.fetch_one("SELECT COUNT(*) AS n FROM ui_actions")
                self.assertEqual(count["n"], 1)
                await database.close()

            asyncio.run(run())

    def test_hydrate_reflects_fresh_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "ui.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_ui_server(database)

                async with InProcessToolbox({"ui": server}) as toolbox:
                    persisted = await toolbox.call(
                        "persist_ui",
                        {
                            "user_id": "u_ana",
                            "domain": "loans_credits",
                            "catalog_id": CATALOG_ID,
                            "components": COMPONENTS,
                            "data_model": DATA_MODEL,
                        },
                    )
                    surface_id = persisted["surface_id"]

                    await database.execute(
                        "UPDATE liabilities SET balance = ? WHERE id = ?", (50000.0, "l_bbva_tdc")
                    )
                    hydrated = await toolbox.call("hydrate_ui", {"surface_id": surface_id})
                    data_message = next(m for m in hydrated["a2ui"] if "updateDataModel" in m)
                    value = data_message["updateDataModel"]["value"]
                    self.assertEqual(value["liabilities"][0]["balance"], 50000.0)
                    self.assertEqual(value["totals"]["debt"], 50000.0 + 35000.0 + 22000.0 + 15000.0 + 7200.0)

                await database.close()

            asyncio.run(run())

    def test_hydrate_unknown_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "ui.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_ui_server(database)
                async with InProcessToolbox({"ui": server}) as toolbox:
                    result = await toolbox.call("hydrate_ui", {"surface_id": "nope"})
                    self.assertEqual(result["status"], "error")
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
