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

__all__ = [
    "BreakReport",
    "FeasibilityResult",
    "Liability",
    "MonthSnapshot",
    "Plan",
    "available_monthly_capacity",
    "compute_feasibility",
    "detect_plan_breaks",
    "monthly_rate",
    "project_completion",
    "simulate",
    "total_min_payment",
]
