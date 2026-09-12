import unittest

from db.schema import schema_statements

EXPECTED_TABLES = {
    "users",
    "accounts",
    "transactions",
    "income_streams",
    "subscriptions",
    "liabilities",
    "lender_policies",
    "saving_bags",
    "saving_bag_answers",
    "saving_bag_research",
    "saving_bag_plan",
    "generated_ui",
    "ui_actions",
    "negotiation_rounds",
    "accessibility_profiles",
    "audio_assets",
    "sessions",
    "traces",
}


class SchemaTest(unittest.TestCase):
    def test_all_required_tables_present(self) -> None:
        combined = " ".join(schema_statements()).lower()
        for table in sorted(EXPECTED_TABLES):
            self.assertIn(f"table if not exists {table}", combined, table)

    def test_statements_are_non_empty(self) -> None:
        statements = schema_statements()
        self.assertTrue(statements)
        self.assertTrue(all(statement.strip() for statement in statements))


if __name__ == "__main__":
    unittest.main()
