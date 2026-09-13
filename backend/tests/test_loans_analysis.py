"""Deterministic, user-specific loan analysis."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from engine import loans_analysis
from mcp_servers.finance import service as finance_service


def _transactions(rows):
    return [
        {
            "occurredOn": row["occurred_on"],
            "amount": row["amount"],
            "direction": row["direction"],
            "category": row["category"],
            "merchant": row["merchant"],
        }
        for row in rows
    ]


class LoansAnalysisTest(unittest.TestCase):
    def test_analysis_is_deterministic_and_user_specific(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "analysis.sqlite3")

            async def run():
                await apply_schema(database)
                await seed(database)
                context = await finance_service.financial_context(database, "u_ana")
                rows = await database.fetch_all(
                    "SELECT occurred_on, amount, direction, category, merchant FROM transactions "
                    "WHERE user_id = 'u_ana' ORDER BY occurred_on DESC LIMIT 120"
                )
                transactions = _transactions(rows)
                first = loans_analysis.analyze(context, transactions=transactions)
                second = loans_analysis.analyze(context, transactions=transactions)
                await database.close()
                return first, second

            first, second = asyncio.run(run())

        self.assertEqual(first, second)  # deterministic
        self.assertEqual(first["monthlyIncome"], 19000.0)
        self.assertEqual(first["minPayment"], 7850.0)
        self.assertEqual(first["capacity"], 0.0)  # seed persona has no surplus
        # Highest-APR credit drives the recommendation.
        self.assertEqual(first["highCost"][0]["creditor"], "Banorte")
        self.assertEqual(first["nextBestAction"]["targetCreditor"], "Banorte")
        # Quincena is tight because income is quincenal.
        self.assertTrue(first["quincena"]["tight"])
        # Behavior is derived from the user's own subscriptions/transactions.
        self.assertGreater(first["behavior"]["subscriptionLoad"]["monthly"], 0)
        self.assertTrue(first["behavior"]["categoryTrends"]["movers"])
        # Scenarios: baseline + presets, all engine-computed and specific.
        steps = [s["extraPayment"] for s in first["scenarios"]]
        self.assertIn(0.0, steps)
        self.assertGreaterEqual(len(steps), 4)
        self.assertIn(950.0, steps)  # subscription leak -> recommended extra
        recommended = next(s for s in first["scenarios"] if s["extraPayment"] == 950.0)
        self.assertGreater(recommended["interestSaved"], 0)
        self.assertGreater(recommended["monthsSaved"], 0)
        # Payoff order is per real creditor.
        self.assertTrue(first["payoffOrder"])
        self.assertIn("creditor", first["payoffOrder"][0])


if __name__ == "__main__":
    unittest.main()
