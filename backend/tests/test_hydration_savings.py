import asyncio
import copy
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from hydration.service import (
    SAVINGS_ALERT_ID,
    SAVINGS_SECTION_ID,
    revalidate_savings,
)
from mcp_servers.savings.server import build_savings_server
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from providers.research import StaticPriceTableResearch

TEMPLATE = [
    {"id": "root", "component": "Column", "children": ["title"], "gap": 12},
    {"id": "title", "component": "Heading", "text": "Mi meta", "level": 1},
]


def _types(components):
    return {c["component"] for c in components}


class RevalidateSavingsTest(unittest.TestCase):
    def test_off_track_adds_alert(self) -> None:
        savings = {"plan": {"feasibility": "off_track"}}
        result = revalidate_savings(copy.deepcopy(TEMPLATE), savings)
        ids = {c["id"] for c in result}
        self.assertIn(SAVINGS_SECTION_ID, ids)
        self.assertIn(SAVINGS_ALERT_ID, ids)
        self.assertIn("GoalJar", _types(result))
        self.assertIn("ProgressBar", _types(result))
        self.assertIn("CashFlowTimeline", _types(result))

    def test_on_track_removes_alert(self) -> None:
        off = revalidate_savings(copy.deepcopy(TEMPLATE), {"plan": {"feasibility": "off_track"}})
        on = revalidate_savings(off, {"plan": {"feasibility": "on_track"}})
        ids = {c["id"] for c in on}
        self.assertNotIn(SAVINGS_ALERT_ID, ids)
        self.assertIn(SAVINGS_SECTION_ID, ids)


class DomainAwareHydrationTest(unittest.TestCase):
    def test_saving_bag_surface_hydrates_with_savings_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "hydrate.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                savings_server = build_savings_server(database, StaticPriceTableResearch())
                ui_server = build_ui_server(database)

                async with InProcessToolbox(
                    {"savings": savings_server, "ui": ui_server}
                ) as toolbox:
                    bag = (
                        await toolbox.call(
                            "create_bag",
                            {
                                "user_id": "u_ana",
                                "name": "Viaje a Japón",
                                "target_amount": 45000.0,
                                "target_date": "2027-04-01",
                            },
                        )
                    )["bag"]["id"]
                    await toolbox.call(
                        "answer_bag",
                        {
                            "bag_id": bag,
                            "answers": [
                                {"question_key": "days", "answer": "10"},
                                {"question_key": "travelers", "answer": "2"},
                                {"question_key": "style", "answer": "mochilero"},
                            ],
                        },
                    )
                    await toolbox.call("research_costs", {"bag_id": bag})
                    await toolbox.call("compute_feasibility", {"bag_id": bag})

                    persisted = await toolbox.call(
                        "persist_ui",
                        {
                            "user_id": "u_ana",
                            "domain": "saving_bag",
                            "catalog_id": "amitie.standard.v1",
                            "components": copy.deepcopy(TEMPLATE),
                            "data_model": {},
                            "entity_id": bag,
                        },
                    )
                    surface = persisted["surface_id"]

                    first = await toolbox.call("hydrate_ui", {"surface_id": surface})
                    self.assertEqual(first["status"], "ok")
                    ids = {
                        c["id"]
                        for m in first["a2ui"]
                        if "updateComponents" in m
                        for c in m["updateComponents"]["components"]
                    }
                    self.assertIn(SAVINGS_SECTION_ID, ids)
                    self.assertIn(SAVINGS_ALERT_ID, ids)
                    self.assertEqual(first["version"], 2)

                    second = await toolbox.call("hydrate_ui", {"surface_id": surface})
                    self.assertEqual(second["version"], 2)

                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
