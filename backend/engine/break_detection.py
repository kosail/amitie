"""Detect when a simulated plan breaks (cash goes negative)."""

from __future__ import annotations

from dataclasses import dataclass

from .amortization import Plan


@dataclass(frozen=True)
class BreakReport:
    month: int
    shortfall: float


def detect_plan_breaks(plan: Plan) -> BreakReport | None:
    for snapshot in plan.months:
        if snapshot.cash < 0:
            return BreakReport(month=snapshot.month, shortfall=round(-snapshot.cash, 2))
    return None
