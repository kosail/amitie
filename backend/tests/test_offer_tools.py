import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox


class OfferToolsTest(unittest.TestCase):
    def test_lender_policies_and_offers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "offer.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    policies = await toolbox.call("get_lender_policies", {})
                    self.assertEqual(len(policies["policies"]), 4)

                    generated = await toolbox.call(
                        "generate_offer", {"user_id": "u_ana", "strategy": "consolidation"}
                    )
                    self.assertEqual(generated["status"], "ok")
                    self.assertEqual(generated["offer"]["principal"], 127200.0)

                    feasible = await toolbox.call(
                        "evaluate_offer",
                        {
                            "user_id": "u_ana",
                            "offer": {
                                "principal": 127200.0,
                                "apr": 0.24,
                                "months": 60,
                                "monthlyPayment": 3500.0,
                            },
                        },
                    )
                    self.assertTrue(feasible["feasible"])

                    infeasible = await toolbox.call(
                        "evaluate_offer",
                        {
                            "user_id": "u_ana",
                            "offer": {
                                "principal": 127200.0,
                                "apr": 0.24,
                                "months": 60,
                                "monthlyPayment": 5000.0,
                            },
                        },
                    )
                    self.assertFalse(infeasible["feasible"])

                    accepted = await toolbox.call(
                        "accept_offer",
                        {"user_id": "u_ana", "offer": {"principal": 127200.0, "monthlyPayment": 3500.0}},
                    )
                    self.assertEqual(accepted["status"], "ok")
                    self.assertTrue(accepted["nextSteps"])

                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
