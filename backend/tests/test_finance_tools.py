import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox


class FinanceToolsTest(unittest.TestCase):
    def test_finance_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "finance.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    profile = await toolbox.call("get_profile", {"user_id": "u_ana"})
                    self.assertEqual(profile["profile"]["name"], "Ana López")
                    self.assertEqual(profile["profile"]["payFrequency"], "quincenal")

                    liabilities = await toolbox.call("get_liabilities", {"user_id": "u_ana"})
                    self.assertEqual(len(liabilities["liabilities"]), 5)
                    self.assertEqual(liabilities["totalDebt"], 127200.0)
                    self.assertEqual(liabilities["totalMinPayment"], 7850.0)
                    self.assertEqual(liabilities["liabilities"][0]["creditor"], "BBVA")

                    income = await toolbox.call("get_income_streams", {"user_id": "u_ana"})
                    self.assertEqual(len(income["incomeStreams"]), 1)

                    subscriptions = await toolbox.call("get_subscriptions", {"user_id": "u_ana"})
                    self.assertEqual(subscriptions["subscriptionTotal"], 947.0)

                    cash_flow = await toolbox.call("get_cash_flow", {"user_id": "u_ana"})
                    self.assertEqual(len(cash_flow["cashFlow"]["months"]), 6)
                    self.assertIn("averageSurplus", cash_flow["cashFlow"])

                    context = await toolbox.call("get_financial_context", {"user_id": "u_ana"})
                    for key in (
                        "profile",
                        "liabilities",
                        "totals",
                        "incomeStreams",
                        "subscriptions",
                        "cashFlow",
                    ):
                        self.assertIn(key, context["context"])

                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
