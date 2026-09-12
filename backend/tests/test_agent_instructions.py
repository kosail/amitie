"""Agent instructions must steer toward engine-backed, non-generic debt UIs."""

import unittest

from agent.service import UI_DESCRIPTION
from agent.loans import LoansConsultService  # noqa: F401  (import sanity)


class InstructionTest(unittest.TestCase):
    def test_debt_flow_uses_engine_analysis(self) -> None:
        self.assertIn("analyze_loans", UI_DESCRIPTION)
        self.assertIn("ScenarioComparison", UI_DESCRIPTION)

    def test_loans_prompt_mandates_engine_numbers(self) -> None:
        # The prompt builder requires a toolbox; construct a minimal stand-in.
        class _Toolbox:
            pass

        service = LoansConsultService(provider=object(), toolbox=_Toolbox())
        prompt = service._system_prompt()
        self.assertIn("Analisis determinista", prompt)
        self.assertIn("ScenarioComparison", prompt)
        self.assertIn("genéricos", prompt)


if __name__ == "__main__":
    unittest.main()
