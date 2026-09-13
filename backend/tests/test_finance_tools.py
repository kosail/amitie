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
                    self.assertEqual(profile["profile"]["educationLevel"], "licenciatura")

                    audience = await toolbox.call("get_audience", {"user_id": "u_ana"})
                    self.assertEqual(audience["audience"]["level"], "detailed")

                    don_audience = await toolbox.call("get_audience", {"user_id": "u_don"})
                    self.assertEqual(don_audience["audience"]["level"], "simple")

                    liabilities = await toolbox.call("get_liabilities", {"user_id": "u_ana"})
                    self.assertEqual(len(liabilities["liabilities"]), 5)
                    self.assertEqual(liabilities["totalDebt"], 127200.0)
                    self.assertEqual(liabilities["totalMinPayment"], 7850.0)
                    self.assertEqual(liabilities["liabilities"][0]["creditor"], "Banorte")

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

    def test_make_payment_moves_real_balances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "finance.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    accounts_before = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    checking = next(
                        a for a in accounts_before["accounts"] if a["kind"] == "checking"
                    )

                    result = await toolbox.call(
                        "make_payment",
                        {"user_id": "u_ana", "liability_id": "l_electronica", "amount": 1000.0},
                    )
                    self.assertEqual(result["status"], "ok")
                    self.assertEqual(result["appliedAmount"], 1000.0)
                    self.assertEqual(result["liability"]["balance"], 6200.0)
                    self.assertEqual(result["liability"]["status"], "active")
                    self.assertEqual(result["account"]["balance"], checking["balance"] - 1000.0)

                    liabilities = await toolbox.call("get_liabilities", {"user_id": "u_ana"})
                    updated = next(
                        item
                        for item in liabilities["liabilities"]
                        if item["id"] == "l_electronica"
                    )
                    self.assertEqual(updated["balance"], 6200.0)

                    # Overpaying beyond the remaining balance clears the liability and
                    # only debits what was actually owed.
                    payoff = await toolbox.call(
                        "make_payment",
                        {"user_id": "u_ana", "liability_id": "l_electronica", "amount": 6200.0},
                    )
                    self.assertEqual(payoff["status"], "ok")
                    self.assertEqual(payoff["liability"]["balance"], 0.0)
                    self.assertEqual(payoff["liability"]["status"], "paid")

                    # Insufficient funds is rejected, not silently clamped.
                    rejected = await toolbox.call(
                        "make_payment",
                        {
                            "user_id": "u_ana",
                            "liability_id": "l_bbva_tdc",
                            "amount": 10_000_000.0,
                        },
                    )
                    self.assertEqual(rejected["status"], "error")

                await database.close()

            asyncio.run(run())


    def test_credit_history_includes_raw_transactions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "finance.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    result = await toolbox.call("get_credit_history", {"user_id": "u_ana"})

                history = result["creditHistory"]
                self.assertTrue(history["recentTransactions"])
                first = history["recentTransactions"][0]
                for key in ("occurredOn", "amount", "direction", "category"):
                    self.assertIn(key, first)
                await database.close()

            asyncio.run(run())


    def test_analyze_loans_returns_engine_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "finance.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    result = await toolbox.call("analyze_loans", {"user_id": "u_ana"})

                analysis = result["analysis"]
                self.assertEqual(analysis["highCost"][0]["creditor"], "Banorte")
                self.assertTrue(analysis["scenarios"])
                self.assertEqual(analysis["nextBestAction"]["targetCreditor"], "Banorte")
                await database.close()

            asyncio.run(run())


    def test_loan_offer_and_create_disburses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "finance.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    offer = await toolbox.call("compute_loan_offer", {"user_id": "u_don"})
                    self.assertGreater(offer["offer"]["offer"]["amount"], 0)

                    created = await toolbox.call(
                        "create_loan", {"user_id": "u_don", "amount": 10000.0}
                    )
                    self.assertEqual(created["status"], "ok")
                    self.assertGreater(len(created["loan"]["schedule"]), 0)

                    accounts = await toolbox.call("get_accounts", {"user_id": "u_don"})
                    checking = next(
                        a for a in accounts["accounts"] if a["kind"] == "checking"
                    )
                    self.assertEqual(checking["balance"], 2100.0 + 10000.0)
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
