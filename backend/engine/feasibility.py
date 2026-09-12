"""Savings feasibility and projection."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class FeasibilityResult:
    monthly_capacity: float
    months_needed: int | None
    on_time: bool
    gap: float


def available_monthly_capacity(
    monthly_income: float, monthly_expenses: float, total_debt_payments: float
) -> float:
    return round(monthly_income - monthly_expenses - total_debt_payments, 2)


def project_completion(
    target_amount: float, monthly_capacity: float, current_saved: float = 0.0
) -> int | None:
    remaining = max(target_amount - current_saved, 0.0)
    if remaining == 0:
        return 0
    if monthly_capacity <= 0:
        return None
    return math.ceil(remaining / monthly_capacity)


def compute_feasibility(
    *,
    target_amount: float,
    current_saved: float,
    monthly_capacity: float,
    months_available: int,
) -> FeasibilityResult:
    months_needed = project_completion(target_amount, monthly_capacity, current_saved)
    on_time = months_needed is not None and months_needed <= months_available
    projected = current_saved + monthly_capacity * months_available
    gap = max(target_amount - projected, 0.0)
    return FeasibilityResult(
        monthly_capacity=monthly_capacity,
        months_needed=months_needed,
        on_time=on_time,
        gap=round(gap, 2),
    )
