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
from .savings import (
    build_savings_plan,
    estimate_total,
    financial_capacity,
    goal_gap,
    months_until,
    style_multiplier,
    suggest_redirect,
)

__all__ = [
    "BreakReport",
    "FeasibilityResult",
    "Liability",
    "MonthSnapshot",
    "Plan",
    "available_monthly_capacity",
    "build_savings_plan",
    "compute_feasibility",
    "detect_plan_breaks",
    "estimate_total",
    "financial_capacity",
    "goal_gap",
    "monthly_rate",
    "months_until",
    "project_completion",
    "simulate",
    "style_multiplier",
    "suggest_redirect",
    "total_min_payment",
]
