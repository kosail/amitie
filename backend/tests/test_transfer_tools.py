import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox

VALID_CLABE = "002180000118359710"
OTHER_VALID_CLABE = "014180001234567897"
INVALID_CLABE = "002180000118359711"  # last digit flipped -> bad checksum


class TransferToolsTest(unittest.TestCase):
    def test_recipients_list_and_create(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def run() -> None:
                database = LocalSQLiteDatabase(Path(tmp) / "recipients.sqlite3")
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    empty = await toolbox.call("list_recipients", {"user_id": "u_ana"})
                    self.assertEqual(empty["recipients"], [])

                    created = await toolbox.call(
                        "create_recipient",
                        {
                            "user_id": "u_ana",
                            "alias": "Mamá",
                            "clabe": VALID_CLABE,
                            "bank_name": "BBVA",
                        },
                    )
                    self.assertEqual(created["status"], "ok")
                    self.assertEqual(created["recipient"]["alias"], "Mamá")
                    self.assertEqual(created["recipient"]["clabe"], VALID_CLABE)

                    listed = await toolbox.call("list_recipients", {"user_id": "u_ana"})
                    self.assertEqual(len(listed["recipients"]), 1)
                    self.assertEqual(listed["recipients"][0]["bankName"], "BBVA")

                    # Invalid CLABE checksum is rejected, not silently accepted.
                    rejected = await toolbox.call(
                        "create_recipient",
                        {
                            "user_id": "u_ana",
                            "alias": "Renta",
                            "clabe": INVALID_CLABE,
                            "bank_name": "Banorte",
                        },
                    )
                    self.assertEqual(rejected["status"], "error")

                await database.close()

            asyncio.run(run())

    def test_own_account_transfer_moves_both_balances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def run() -> None:
                database = LocalSQLiteDatabase(Path(tmp) / "own.sqlite3")
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    accounts = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    checking = next(a for a in accounts["accounts"] if a["kind"] == "checking")
                    savings = next(a for a in accounts["accounts"] if a["kind"] == "savings")

                    result = await toolbox.call(
                        "transfer_funds",
                        {
                            "user_id": "u_ana",
                            "source_account_id": checking["id"],
                            "amount": 500.0,
                            "memo": "Ahorro del mes",
                            "destination": {"kind": "own", "account_id": savings["id"]},
                        },
                    )
                    self.assertEqual(result["status"], "ok")
                    self.assertEqual(result["sourceAccount"]["balance"], checking["balance"] - 500.0)
                    self.assertEqual(
                        result["destinationAccount"]["balance"], savings["balance"] + 500.0
                    )

                    # Both sides actually persisted, not just returned in the response.
                    accounts_after = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    checking_after = next(
                        a for a in accounts_after["accounts"] if a["id"] == checking["id"]
                    )
                    savings_after = next(
                        a for a in accounts_after["accounts"] if a["id"] == savings["id"]
                    )
                    self.assertEqual(checking_after["balance"], checking["balance"] - 500.0)
                    self.assertEqual(savings_after["balance"], savings["balance"] + 500.0)

                    # Two transaction rows recorded (one debit, one credit).
                    rows = await database.fetch_all(
                        "SELECT * FROM transactions WHERE category = 'transfer_own' "
                        "ORDER BY direction",
                        (),
                    )
                    self.assertEqual(len(rows), 2)
                    directions = {row["direction"] for row in rows}
                    self.assertEqual(directions, {"in", "out"})
                    for row in rows:
                        self.assertEqual(row["memo"], "Ahorro del mes")

                await database.close()

            asyncio.run(run())

    def test_external_transfer_only_debits_source_and_can_save_recipient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def run() -> None:
                database = LocalSQLiteDatabase(Path(tmp) / "external.sqlite3")
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    accounts = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    checking = next(a for a in accounts["accounts"] if a["kind"] == "checking")
                    savings = next(a for a in accounts["accounts"] if a["kind"] == "savings")

                    result = await toolbox.call(
                        "transfer_funds",
                        {
                            "user_id": "u_ana",
                            "source_account_id": checking["id"],
                            "amount": 250.0,
                            "memo": "Renta de septiembre",
                            "destination": {
                                "kind": "external",
                                "clabe": OTHER_VALID_CLABE,
                                "bank_name": "Santander",
                                "alias": "Casero",
                                "save_recipient": True,
                            },
                        },
                    )
                    self.assertEqual(result["status"], "ok")
                    self.assertEqual(result["sourceAccount"]["balance"], checking["balance"] - 250.0)
                    self.assertIsNone(result["destinationAccount"])
                    self.assertIsNotNone(result["savedRecipient"])
                    self.assertEqual(result["savedRecipient"]["alias"], "Casero")

                    # No other account in the system changed.
                    accounts_after = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    savings_after = next(
                        a for a in accounts_after["accounts"] if a["id"] == savings["id"]
                    )
                    self.assertEqual(savings_after["balance"], savings["balance"])

                    # Only one transaction row for an external transfer.
                    rows = await database.fetch_all(
                        "SELECT * FROM transactions WHERE category = 'transfer_external'", ()
                    )
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["direction"], "out")

                    # Recipient actually persisted.
                    recipients = await toolbox.call("list_recipients", {"user_id": "u_ana"})
                    self.assertEqual(len(recipients["recipients"]), 1)
                    self.assertEqual(recipients["recipients"][0]["clabe"], OTHER_VALID_CLABE)

                await database.close()

            asyncio.run(run())

    def test_insufficient_funds_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def run() -> None:
                database = LocalSQLiteDatabase(Path(tmp) / "insufficient.sqlite3")
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    accounts = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    checking = next(a for a in accounts["accounts"] if a["kind"] == "checking")

                    result = await toolbox.call(
                        "transfer_funds",
                        {
                            "user_id": "u_ana",
                            "source_account_id": checking["id"],
                            "amount": 10_000_000.0,
                            "memo": "Demasiado",
                            "destination": {
                                "kind": "external",
                                "clabe": VALID_CLABE,
                                "bank_name": "BBVA",
                                "alias": "Mamá",
                                "save_recipient": False,
                            },
                        },
                    )
                    self.assertEqual(result["status"], "error")

                    # Balance untouched.
                    accounts_after = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    checking_after = next(
                        a for a in accounts_after["accounts"] if a["id"] == checking["id"]
                    )
                    self.assertEqual(checking_after["balance"], checking["balance"])

                await database.close()

            asyncio.run(run())

    def test_invalid_clabe_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def run() -> None:
                database = LocalSQLiteDatabase(Path(tmp) / "badclabe.sqlite3")
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    accounts = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    checking = next(a for a in accounts["accounts"] if a["kind"] == "checking")

                    result = await toolbox.call(
                        "transfer_funds",
                        {
                            "user_id": "u_ana",
                            "source_account_id": checking["id"],
                            "amount": 100.0,
                            "memo": "CLABE mala",
                            "destination": {
                                "kind": "external",
                                "clabe": INVALID_CLABE,
                                "bank_name": "BBVA",
                                "alias": "Mamá",
                                "save_recipient": False,
                            },
                        },
                    )
                    self.assertEqual(result["status"], "error")

                await database.close()

            asyncio.run(run())

    def test_same_account_both_sides_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def run() -> None:
                database = LocalSQLiteDatabase(Path(tmp) / "sameaccount.sqlite3")
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    accounts = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    checking = next(a for a in accounts["accounts"] if a["kind"] == "checking")

                    result = await toolbox.call(
                        "transfer_funds",
                        {
                            "user_id": "u_ana",
                            "source_account_id": checking["id"],
                            "amount": 50.0,
                            "memo": "A mi misma cuenta",
                            "destination": {"kind": "own", "account_id": checking["id"]},
                        },
                    )
                    self.assertEqual(result["status"], "error")

                await database.close()

            asyncio.run(run())

    def test_own_transfer_rejects_destination_belonging_to_another_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def run() -> None:
                database = LocalSQLiteDatabase(Path(tmp) / "crossuser.sqlite3")
                await apply_schema(database)
                await seed(database)
                server = build_finance_server(database)

                async with InProcessToolbox({"finance": server}) as toolbox:
                    ana_accounts = await toolbox.call("get_accounts", {"user_id": "u_ana"})
                    checking = next(a for a in ana_accounts["accounts"] if a["kind"] == "checking")
                    don_accounts = await toolbox.call("get_accounts", {"user_id": "u_don"})
                    don_checking = don_accounts["accounts"][0]

                    result = await toolbox.call(
                        "transfer_funds",
                        {
                            "user_id": "u_ana",
                            "source_account_id": checking["id"],
                            "amount": 50.0,
                            "memo": "No debería funcionar",
                            "destination": {"kind": "own", "account_id": don_checking["id"]},
                        },
                    )
                    self.assertEqual(result["status"], "error")

                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
