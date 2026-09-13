"""Deterministic loan offer + risk framework."""

import unittest

from engine import loan_offer

CONTEXT = {
    "profile": {"monthlyIncome": 30000.0, "payFrequency": "quincenal"},
    "liabilities": [
        {"id": "l1", "creditor": "BBVA", "balance": 50000.0, "apr": 0.5, "minPayment": 2000.0}
    ],
    "subscriptions": [{"amount": 300.0, "period": "mensual"}],
    "cashFlow": {
        "months": [
            {"income": 30000.0, "expenses": 12000.0, "net": 18000.0},
            {"income": 30000.0, "expenses": 13000.0, "net": 17000.0},
        ]
    },
    "subscriptionTotal": 300.0,
}

POLICIES = [{"creditor": "BBVA", "strategy": "consolidation", "aprFloor": 0.24}]
GOALS = [{"name": "Viaje a Japón", "targetAmount": 45000.0, "currentSaved": 0.0}]
HISTORY = [{"status": "on_time"}] * 5 + [{"status": "late"}]

STRONG_CONTEXT = {
    "profile": {"monthlyIncome": 40000.0, "payFrequency": "mensual"},
    "liabilities": [
        {"id": "l1", "creditor": "BBVA", "balance": 10000.0, "apr": 0.2, "minPayment": 500.0}
    ],
    "subscriptions": [],
    "cashFlow": {
        "months": [
            {"income": 40000.0, "expenses": 8000.0, "net": 32000.0},
            {"income": 40000.0, "expenses": 8000.0, "net": 32000.0},
            {"income": 40000.0, "expenses": 8000.0, "net": 32000.0},
        ]
    },
    "subscriptionTotal": 0.0,
}
STRONG_ACCOUNTS = [{"balance": 120000.0}]
STRONG_HISTORY = [{"status": "on_time"}] * 12

RISKY_CONTEXT = {
    "profile": {"monthlyIncome": 30000.0, "payFrequency": "quincenal"},
    "liabilities": [
        {"id": "l1", "creditor": "BBVA", "balance": 90000.0, "apr": 0.6, "minPayment": 5000.0}
    ],
    "subscriptions": [{"amount": 1500.0, "period": "mensual"}],
    "cashFlow": {
        "months": [
            {"income": 30000.0, "expenses": 14000.0, "net": 16000.0},
            {"income": 20000.0, "expenses": 15000.0, "net": 5000.0},
            {"income": 35000.0, "expenses": 13000.0, "net": 22000.0},
        ]
    },
    "subscriptionTotal": 1500.0,
}
RISKY_ACCOUNTS = [{"balance": 3000.0}]
RISKY_HISTORY = [{"status": "late"}, {"status": "missed"}, {"status": "on_time"}]


class LoanOfferTest(unittest.TestCase):
    def test_offer_is_deterministic_and_affordable(self) -> None:
        first = loan_offer.propose_offer(CONTEXT, lender_policies=POLICIES)
        second = loan_offer.propose_offer(CONTEXT, lender_policies=POLICIES)
        self.assertEqual(first, second)

        offer = first["offer"]
        self.assertGreater(offer["amount"], 0)
        self.assertEqual(len(first["schedule"]), offer["termMonths"])
        # DTI stays within the cap.
        self.assertLessEqual(first["risk"]["dti"]["withOffer"], first["risk"]["dti"]["cap"] + 1e-9)
        self.assertTrue(first["affordable"])
        # CAT includes fees, so it exceeds the APR.
        self.assertGreater(offer["cat"], offer["apr"])
        self.assertGreater(first["risk"]["surplus"]["monthly"], 0)

    def test_requested_amount_caps_and_rounds(self) -> None:
        small = loan_offer.propose_offer(CONTEXT, requested_amount=8000.0)
        self.assertEqual(small["offer"]["amount"], 8000.0)
        huge = loan_offer.propose_offer(CONTEXT, requested_amount=10_000_000.0)
        self.assertLess(huge["offer"]["amount"], 10_000_000.0)

    def test_relative_cost_and_history_and_savings(self) -> None:
        result = loan_offer.propose_offer(
            CONTEXT,
            lender_policies=POLICIES,
            saving_goals=GOALS,
            payment_history=HISTORY,
        )
        # Offered APR (24%) beats the existing 50% credit -> not worse.
        self.assertFalse(result["risk"]["relativeCost"]["worse"])
        self.assertTrue(result["risk"]["paymentHistory"]["available"])
        self.assertLess(result["risk"]["paymentHistory"]["projectedScoreDelta"], 8)
        self.assertIsNotNone(result["risk"]["savingsImpact"])

    def test_compute_cat_zero_for_zero_amount(self) -> None:
        self.assertEqual(loan_offer.compute_cat(0, 0.24, 24, 0, 0), 0.0)

    def test_term_options_are_engine_backed(self) -> None:
        # 10,000 is a small amount -> short band, plus the offered/recommended term.
        options = loan_offer.term_options(10_000.0, apr=0.24, recommended_months=24)
        self.assertEqual([o["months"] for o in options], [6, 12, 24])
        for option in options:
            terms = loan_offer.terms_for(10_000.0, apr=0.24, term_months=option["months"])
            self.assertEqual(option["monthlyPayment"], terms["monthlyPayment"])
            self.assertEqual(option["totalInterest"], terms["totalInterest"])
            self.assertGreater(option["monthlyPayment"], 0)
            self.assertGreater(option["totalInterest"], 0)
            self.assertEqual(option["label"], f"{option['months']} meses")
        # Shorter terms cost more per month but less total interest.
        self.assertGreater(options[0]["monthlyPayment"], options[-1]["monthlyPayment"])
        self.assertLess(options[0]["totalInterest"], options[-1]["totalInterest"])
        self.assertEqual([o["months"] for o in options if o["recommended"]], [24])

    def test_allowed_terms_shrink_with_amount(self) -> None:
        self.assertEqual(loan_offer.allowed_terms_for(8_000.0), [6, 12])
        self.assertEqual(loan_offer.allowed_terms_for(30_000.0), [6, 12, 24])
        self.assertEqual(loan_offer.allowed_terms_for(80_000.0), [12, 24, 36])
        self.assertEqual(loan_offer.allowed_terms_for(200_000.0), [12, 24, 36, 48])

    def test_requested_term_is_kept_and_selected(self) -> None:
        options = loan_offer.term_options(8_000.0, recommended_months=12, requested_term=24)
        self.assertIn(24, [o["months"] for o in options])
        result = loan_offer.propose_offer(CONTEXT, requested_amount=8000.0, requested_term=24)
        self.assertEqual(result["offer"]["termMonths"], 24)
        self.assertEqual(result["recommendation"]["requested"], 24)
        requested = [o for o in result["options"] if o["requested"]]
        self.assertEqual(len(requested), 1)
        self.assertTrue(requested[0]["recommended"])

    def test_term_options_empty_without_amount(self) -> None:
        self.assertEqual(loan_offer.term_options(0.0), [])

    def test_propose_offer_includes_options(self) -> None:
        result = loan_offer.propose_offer(CONTEXT, requested_amount=8000.0)
        allowed = loan_offer.allowed_terms_for(result["offer"]["amount"])
        months = [option["months"] for option in result["options"]]
        self.assertTrue(set(allowed).issubset(set(months)))
        self.assertEqual(len([option for option in result["options"] if option["recommended"]]), 1)

    def test_recommended_term_drives_the_offer(self) -> None:
        result = loan_offer.propose_offer(
            CONTEXT, accounts=STRONG_ACCOUNTS, payment_history=STRONG_HISTORY
        )
        recommended = [option for option in result["options"] if option["recommended"]]
        self.assertEqual(len(recommended), 1)
        chosen = recommended[0]
        self.assertEqual(result["offer"]["termMonths"], chosen["months"])
        self.assertEqual(result["offer"]["monthlyPayment"], chosen["monthlyPayment"])
        self.assertEqual(result["offer"]["totalInterest"], chosen["totalInterest"])
        self.assertTrue(chosen.get("reason"))
        self.assertIn("Recomendamos", result["recommendation"]["text"])
        self.assertEqual(result["recommendation"]["months"], chosen["months"])

    def test_recommendation_varies_with_profile(self) -> None:
        strong = loan_offer.propose_offer(
            STRONG_CONTEXT,
            accounts=STRONG_ACCOUNTS,
            payment_history=STRONG_HISTORY,
            requested_amount=8000.0,
        )
        risky = loan_offer.propose_offer(
            RISKY_CONTEXT,
            accounts=RISKY_ACCOUNTS,
            payment_history=RISKY_HISTORY,
            requested_amount=8000.0,
        )
        self.assertLess(strong["recommendation"]["risk"], risky["recommendation"]["risk"])
        self.assertNotEqual(strong["recommendation"]["months"], risky["recommendation"]["months"])

    def test_smaller_amount_does_not_lengthen_term(self) -> None:
        at_cap = loan_offer.propose_offer(
            STRONG_CONTEXT, accounts=STRONG_ACCOUNTS, payment_history=STRONG_HISTORY
        )
        small = loan_offer.propose_offer(
            STRONG_CONTEXT,
            accounts=STRONG_ACCOUNTS,
            payment_history=STRONG_HISTORY,
            requested_amount=6000.0,
        )
        self.assertLessEqual(small["recommendation"]["months"], at_cap["recommendation"]["months"])


if __name__ == "__main__":
    unittest.main()
