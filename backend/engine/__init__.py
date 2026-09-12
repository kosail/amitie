"""Deterministic financial engines (INV-015).

Pure functions only: no IO, no database, no LLM. The orchestrator decides
strategy; these modules compute the numbers.
"""

from .amortization import Liability, MonthSnapshot, Plan, monthly_rate, simulate, total_min_payment
from .break_detection import BreakReport, detect_plan_breaks
from .feasibility import (
    FeasibilityResult,
    available_monthly_capacity,
    compute_feasibility,
    project_completion,
)
from .loans_analysis import analyze as analyze_loans
from .loan_offer import compute_cat, propose_offer, terms_for

__all__ = [
    "BreakReport",
    "FeasibilityResult",
    "Liability",
    "MonthSnapshot",
    "Plan",
    "available_monthly_capacity",
    "analyze_loans",
    "compute_cat",
    "compute_feasibility",
    "detect_plan_breaks",
    "monthly_rate",
    "propose_offer",
    "project_completion",
    "simulate",
    "terms_for",
    "total_min_payment",
]
