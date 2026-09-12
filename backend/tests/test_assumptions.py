import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from hydration.assumptions import SECTION_ID, build_assumption_components
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server

DEBT_CONTEXT = {
    "profile": {"monthlyIncome": 19000.0},
    "cashFlow": {"months": [{"expenses": 15000.0}]},
    "liabilities": [{"minPayment": 7850.0}],
    "plan": {},
}


def _by_id(components, component_id):
    return next(c for c in components if c.get("id") == component_id)


class AssumptionsPureTest(unittest.TestCase):
    def test_debt_assumptions(self) -> None:
        components = build_assumption_components(
            DEBT_CONTEXT, simulation={"strategy": "avalanche", "extra_income": 0}
        )
        section = _by_id(components, SECTION_ID)
        self.assertEqual(section["component"], "Card")
        self.assertIn("¿Por qué ves esto?", section["title"])

        chip = _by_id(components, "assumption-extra_income")
        self.assertTrue(chip["editable"])
        self.assertEqual(chip["action"]["event"]["name"], "toggle_assumption")
        self.assertEqual(chip["action"]["event"]["context"]["key"], "extra_income")

        self.assertFalse(_by_id(components, "assumption-monthlyIncome").get("editable"))

    def test_no_assumptions_without_plan(self) -> None:
        self.assertEqual(build_assumption_components({}), [])


class AssumptionsHydrationTest(unittest.TestCase):
    def test_hydrated_surface_has_editable_panel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "assump.sqlite3")

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
                                {"id": "root", "component": "Column", "children": ["t"], "gap": 12},
                                {"id": "t", "component": "Heading", "text": "Tu plan"},
                            ],
                            "data_model": {},
                            "simulation": {"strategy": "avalanche"},
                        },
                    )
                    hydrated = await toolbox.call(
                        "hydrate_ui", {"surface_id": persisted["surface_id"]}
                    )
                    components = next(
                        m for m in hydrated["a2ui"] if "updateComponents" in m
                    )["updateComponents"]["components"]
                    ids = {c["id"] for c in components}
                    self.assertIn(SECTION_ID, ids)
                    self.assertIn("assumption-extra_payment", ids)
                    self.assertTrue(
                        next(c for c in components if c["id"] == "assumption-extra_payment")["editable"]
                    )
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
