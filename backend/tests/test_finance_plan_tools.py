import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox


class FinancePlanToolsTest(unittest.TestCase):
    def test_simulate_and_detect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "plan.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    simulated = await toolbox.call(
                        "simulate_plan", {"user_id": "u_ana", "strategy": "avalanche"}
                    )
                    self.assertEqual(simulated["break"]["month"], 1)
                    self.assertAlmostEqual(simulated["break"]["shortfall"], 4217.09, places=2)
                    self.assertEqual(simulated["inputs"]["monthlyIncome"], 19000.0)

                    detected = await toolbox.call(
                        "detect_plan_breaks", {"user_id": "u_ana", "strategy": "avalanche"}
                    )
                    self.assertEqual(detected["breakMonth"], 1)
                    self.assertAlmostEqual(detected["shortfall"], 4217.09, places=2)

                    repaired = await toolbox.call(
                        "simulate_plan",
                        {"user_id": "u_ana", "strategy": "avalanche", "extra_income": 8000},
                    )
                    self.assertIsNone(repaired["break"])
                    self.assertIsNone(
                        (
                            await toolbox.call(
                                "detect_plan_breaks",
                                {"user_id": "u_ana", "strategy": "avalanche", "extra_income": 8000},
                            )
                        )["break"]
                    )

                    repeat = await toolbox.call(
                        "simulate_plan", {"user_id": "u_ana", "strategy": "avalanche"}
                    )
                    self.assertEqual(repeat["break"], simulated["break"])

                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
