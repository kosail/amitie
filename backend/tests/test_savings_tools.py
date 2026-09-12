import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.savings.server import build_savings_server
from mcp_servers.toolbox import InProcessToolbox
from providers.research import StaticPriceTableResearch

ANSWERS = [
    {"question_key": "when", "answer": "abril 2027"},
    {"question_key": "days", "answer": "10"},
    {"question_key": "travelers", "answer": "2"},
    {"question_key": "style", "answer": "mochilero"},
]


class SavingsToolsTest(unittest.TestCase):
    def test_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "savings.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_savings_server(database, StaticPriceTableResearch())

                async with InProcessToolbox({"savings": server}) as toolbox:
                    created = await toolbox.call(
                        "create_bag",
                        {
                            "user_id": "u_ana",
                            "name": "Viaje a Japón",
                            "target_amount": 45000.0,
                            "target_date": "2027-04-01",
                        },
                    )
                    bag_id = created["bag"]["id"]

                    listed = await toolbox.call("list_bags", {"user_id": "u_ana"})
                    self.assertIn(bag_id, [bag["id"] for bag in listed["bags"]])

                    answered = await toolbox.call(
                        "answer_bag", {"bag_id": bag_id, "answers": ANSWERS}
                    )
                    self.assertEqual(answered["answers"]["style"], "mochilero")

                    researched = await toolbox.call("research_costs", {"bag_id": bag_id})
                    self.assertEqual(researched["research"]["source"], "static_table")
                    self.assertEqual(
                        researched["research"]["payload"]["flight_roundtrip_mxn"], 28000.0
                    )

                    estimate = await toolbox.call("estimate_total", {"bag_id": bag_id})
                    self.assertEqual(estimate["estimatedTotal"], 77088.0)
                    self.assertEqual(estimate["goal"]["status"], "over")

                    feasibility = await toolbox.call(
                        "compute_feasibility", {"bag_id": bag_id}
                    )
                    self.assertEqual(feasibility["plan"]["feasibility"], "off_track")
                    self.assertTrue(feasibility["plan"]["redirect"]["recommended"])

                    snapshot = await toolbox.call("get_savings_snapshot", {"bag_id": bag_id})
                    self.assertEqual(snapshot["savings"]["plan"]["bagId"], bag_id)

                await database.close()

            asyncio.run(run())

    def test_research_snapshots_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "snapshots.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_savings_server(database, StaticPriceTableResearch())

                async with InProcessToolbox({"savings": server}) as toolbox:
                    created = await toolbox.call(
                        "create_bag",
                        {"user_id": "u_ana", "name": "Viaje a Japón", "target_amount": 45000.0},
                    )
                    bag_id = created["bag"]["id"]
                    await toolbox.call("research_costs", {"bag_id": bag_id})
                    await toolbox.call("research_costs", {"bag_id": bag_id})

                rows = await database.fetch_all(
                    "SELECT id FROM saving_bag_research WHERE bag_id = ?", (bag_id,)
                )
                self.assertEqual(len(rows), 2)
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
