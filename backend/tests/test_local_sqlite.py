import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed


class LocalSQLiteDatabaseTest(unittest.TestCase):
    def test_schema_seed_and_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "local.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)

                users = await database.fetch_all("SELECT id FROM users ORDER BY id")
                self.assertEqual(
                    [row["id"] for row in users],
                    ["u_ana", "u_carmen", "u_don", "u_roberto", "u_sofia"],
                )

                count = await database.fetch_one("SELECT COUNT(*) AS n FROM transactions")
                self.assertEqual(count["n"], 294)

                total = await database.fetch_one(
                    "SELECT SUM(balance) AS total FROM liabilities WHERE user_id = ?",
                    ("u_ana",),
                )
                self.assertAlmostEqual(total["total"], 127200.0)

                bag = await database.fetch_one("SELECT name FROM saving_bags WHERE id = ?", ("bag_japon",))
                self.assertEqual(bag["name"], "Viaje a Japón")

                profile = await database.fetch_one(
                    "SELECT mode FROM accessibility_profiles WHERE user_id = ?", ("u_don",)
                )
                self.assertEqual(profile["mode"], "low_literacy")

                await database.close()

            asyncio.run(run())

    def test_seed_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "local.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                await seed(database)
                users = await database.fetch_one("SELECT COUNT(*) AS n FROM users")
                tickets = await database.fetch_one("SELECT COUNT(*) AS n FROM transactions")
                self.assertEqual(users["n"], 5)
                self.assertEqual(tickets["n"], 294)
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
