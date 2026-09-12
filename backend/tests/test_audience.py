import unittest

from engine.audience import classify


class AudienceTest(unittest.TestCase):
    def test_basic_education_yields_simple(self) -> None:
        result = classify(
            {"age": 71, "educationLevel": "primaria"},
            accessibility_mode="low_literacy",
            transaction_count=5,
            liability_count=1,
        )
        self.assertEqual(result["level"], "simple")
        self.assertEqual(result["comprehension"], "basic")
        self.assertTrue(result["explainTerms"])
        self.assertFalse(result["showAdvancedMetrics"])
        self.assertFalse(result["showCharts"])
        self.assertEqual(result["maxSections"], 2)
        self.assertIn("BÁSICA", result["directive"])

    def test_advanced_with_activity_yields_detailed(self) -> None:
        result = classify(
            {"age": 32, "educationLevel": "licenciatura"},
            transaction_count=60,
            distinct_categories=8,
            liability_count=5,
        )
        self.assertEqual(result["level"], "detailed")
        self.assertTrue(result["showAdvancedMetrics"])
        self.assertTrue(result["showCharts"])
        self.assertEqual(result["maxSections"], 6)

    def test_advanced_low_activity_is_standard(self) -> None:
        result = classify(
            {"age": 30, "educationLevel": "posgrado"},
            transaction_count=4,
            liability_count=1,
            account_count=1,
        )
        self.assertEqual(result["level"], "standard")

    def test_elderly_forces_simple_regardless_of_education(self) -> None:
        result = classify(
            {"age": 70, "educationLevel": "licenciatura"}, transaction_count=80
        )
        self.assertEqual(result["level"], "simple")

    def test_deterministic(self) -> None:
        profile = {"age": 40, "educationLevel": "preparatoria"}
        first = classify(profile, transaction_count=20)
        second = classify(profile, transaction_count=20)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
