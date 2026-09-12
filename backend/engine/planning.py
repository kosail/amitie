"""Context -> engine adapter and plan payloads.

Pure functions shared by the finance MCP tools and structural revalidation so
the plan is computed exactly once, deterministically (INV-015).
"""

from __future__ import annotations

from typing import Any, Mapping

from .amortization import Liability, Plan, simulate
from .break_detection import detect_plan_breaks

DEFAULT_STRATEGY = "avalanche"


def _monthly_amount(stream: Mapping[str, Any]) -> float:
    amount = float(stream.get("amount") or 0.0)
    frequency = str(stream.get("frequency") or "").lower()
    if frequency in ("quincenal", "biweekly", "catorcenal"):
        return amount * 2
    return amount


def liabilities_from_context(context: Mapping[str, Any]) -> list[Liability]:
    items = context.get("liabilities") or []
    return [
        Liability(
            id=str(item.get("id") or f"l{index}"),
            creditor=str(item.get("creditor") or ""),
            balance=float(item.get("balance") or 0.0),
            apr=float(item.get("apr") or 0.0),
            min_payment=float(item.get("minPayment") or 0.0),
        )
        for index, item in enumerate(items)
    ]


def monthly_cashflow(context: Mapping[str, Any]) -> tuple[float, float]:
    profile = context.get("profile") or {}
    income = float(profile.get("monthlyIncome") or 0.0)
    if income <= 0:
        income = sum(_monthly_amount(stream) for stream in (context.get("incomeStreams") or []))

    cash_flow = context.get("cashFlow") or {}
    months = cash_flow.get("months") or []
    expenses = (
        sum(float(month.get("expenses") or 0.0) for month in months) / len(months)
        if months
        else 0.0
    )
    return income, round(expenses, 2)


def simulation_inputs(context: Mapping[str, Any]) -> dict[str, float]:
    income, expenses = monthly_cashflow(context)
    liabilities = liabilities_from_context(context)
    return {
        "monthlyIncome": income,
        "monthlyExpenses": expenses,
        "minPayment": round(sum(item.min_payment for item in liabilities), 2),
    }


def run_simulation(
    context: Mapping[str, Any],
    *,
    strategy: str = DEFAULT_STRATEGY,
    extra_payment: float = 0.0,
    extra_income: float = 0.0,
    expense_reduction: float = 0.0,
    horizon_months: int = 36,
    events: Mapping[Any, Any] | None = None,
) -> Plan:
    income, expenses = monthly_cashflow(context)
    return simulate(
        monthly_income=income + float(extra_income or 0.0),
        monthly_expenses=max(expenses - float(expense_reduction or 0.0), 0.0),
        liabilities=liabilities_from_context(context),
        strategy=strategy,
        horizon_months=int(horizon_months or 36),
        extra_payment=float(extra_payment or 0.0),
        events={int(key): float(value) for key, value in (events or {}).items()},
    )


def plan_payload(plan: Plan) -> dict[str, Any]:
    return {
        "strategy": plan.strategy,
        "months": [
            {
                "month": snap.month,
                "totalBalance": snap.total_balance,
                "payment": snap.payment,
                "interest": snap.interest,
                "cash": snap.cash,
            }
            for snap in plan.months
        ],
        "totalInterest": plan.total_interest,
        "totalPaid": plan.total_paid,
        "payoffMonth": plan.payoff_month,
    }


def break_payload(plan: Plan) -> dict[str, Any] | None:
    report = detect_plan_breaks(plan)
    if report is None:
        return None
    return {"month": report.month, "shortfall": report.shortfall}


def build_plan(context: Mapping[str, Any], simulation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the `/plan` data model used by `PlanTable` and `BreakAlert`."""
    simulation = simulation or {}
    plan = run_simulation(
        context,
        strategy=str(simulation.get("strategy") or DEFAULT_STRATEGY),
        extra_payment=float(simulation.get("extra_payment") or 0.0),
        extra_income=float(simulation.get("extra_income") or 0.0),
        expense_reduction=float(simulation.get("expense_reduction") or 0.0),
        horizon_months=int(simulation.get("horizon_months") or 36),
        events=simulation.get("events"),
    )
    breakdown = break_payload(plan)
    payload = plan_payload(plan)
    payload["breakMonth"] = breakdown["month"] if breakdown else None
    payload["break"] = breakdown
    return payload
