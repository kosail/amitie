import unittest

from db.seed import build_seed_statements


class SeedTest(unittest.TestCase):
    def test_seed_is_deterministic(self) -> None:
        self.assertEqual(build_seed_statements(), build_seed_statements())

    def test_seed_covers_showcase_entities(self) -> None:
        statements = build_seed_statements()
        tables = [sql.split()[2] for sql, _ in statements]
        for table in ("users", "liabilities", "saving_bags", "accessibility_profiles", "transactions"):
            self.assertIn(table, tables)

        transactions = [params for sql, params in statements if sql.startswith("INSERT INTO transactions")]
        self.assertEqual(len(transactions), 294)

        users = [params for sql, params in statements if sql.startswith("INSERT INTO users")]
        self.assertEqual(len(users), 5)


if __name__ == "__main__":
    unittest.main()
