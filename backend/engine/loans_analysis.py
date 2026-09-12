"""Deterministic, user-specific loan analysis (INV-015).

Turns the user's real financial context and transaction behavior into the
scenarios and insights the loans UI presents. Pure functions only: the LLM
narrates and lays out the result; it never computes the numbers.
"""

from __future__ import annotations

from statistics import pstdev
from typing import Any, Mapping

from . import planning
from .amortization import Plan, simulate

DEFAULT_HORIZON = 60
_PRESET_STEPS = (500.0, 1000.0, 2000.0)


def _r(value: Any) -> float:
    return round(float(value), 2)


def _money(value: float) -> str:
    return f"${float(value):,.0f}"


def _scenario_steps(capacity: float) -> list[float]:
    steps = {0.0, *_PRESET_STEPS}
    if capacity > 0:
        steps.add(float(round(capacity)))
    return sorted(steps)


def _category_trends(transactions: Any, months: int = 2) -> dict[str, Any]:
    buckets: dict[str, dict[str, float]] = {}
    for txn in transactions or []:
        if txn.get("direction") != "out":
            continue
        period = str(txn.get("occurredOn") or "")[:7]
        category = str(txn.get("category") or "otros")
        buckets.setdefault(category, {})
        buckets[category][period] = buckets[category].get(period, 0.0) + float(
            txn.get("amount") or 0.0
        )
    periods = sorted({period for values in buckets.values() for period in values})[-months:]
    movers: list[dict[str, Any]] = []
    if len(periods) == months:
        latest, prior = periods[-1], periods[-2]
        for category, by_period in buckets.items():
            delta = by_period.get(latest, 0.0) - by_period.get(prior, 0.0)
            if abs(delta) >= 1:
                movers.append(
                    {
                        "category": category,
                        "latest": _r(by_period.get(latest, 0.0)),
                        "previous": _r(by_period.get(prior, 0.0)),
                        "delta": _r(delta),
                    }
                )
    movers.sort(key=lambda item: abs(item["delta"]), reverse=True)
    return {
        "latestPeriod": periods[-1] if periods else None,
        "previousPeriod": periods[-2] if len(periods) > 1 else None,
        "movers": movers[:5],
    }


def _payoff_order(plan: Plan, liabilities: list[Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_id = {item.id: item for item in liabilities}
    order = []
    for liability_id, month in sorted(plan.payoff_months.items(), key=lambda kv: kv[1]):
        liability = by_id.get(liability_id)
        if liability is None:
            continue
        order.append(
            {
                "creditor": liability.creditor,
                "kind": (meta.get(liability_id) or {}).get("kind"),
                "balance": _r(liability.balance),
                "apr": _r(liability.apr),
                "monthlyPayment": _r(liability.min_payment),
                "payoffMonth": month,
            }
        )
    return order


def analyze(
    context: Mapping[str, Any],
    *,
    strategy: str = "avalanche",
    horizon_months: int = DEFAULT_HORIZON,
    transactions: Any = None,
) -> dict[str, Any]:
    income, expenses = planning.monthly_cashflow(context)
    liabilities = planning.liabilities_from_context(context)
    meta = {str(item.get("id")): item for item in (context.get("liabilities") or [])}
    min_payment = _r(sum(item.min_payment for item in liabilities))
    capacity = _r(max(income - expenses - min_payment, 0.0))
    subscriptions_total = _r(
        context.get("subscriptionTotal")
        or sum(float(item.get("amount") or 0) for item in (context.get("subscriptions") or []))
    )

    def run(extra: float, strat: str = strategy) -> Plan:
        return simulate(
            monthly_income=income,
            monthly_expenses=expenses,
            liabilities=liabilities,
            strategy=strat,
            horizon_months=horizon_months,
            extra_payment=extra,
        )

    baseline = run(0.0)

    def make_scenario(step: float, prefix: str = "") -> dict[str, Any]:
        plan = run(step)
        label = "Pago mínimo" if step == 0 else f"{prefix}Abono extra {_money(step)}/mes"
        return {
            "label": label,
            "extraPayment": _r(step),
            "monthlyPayment": _r(min_payment + step),
            "payoffMonths": plan.payoff_month,
            "totalInterest": plan.total_interest,
            "interestSaved": _r(baseline.total_interest - plan.total_interest),
            "monthsSaved": (
                baseline.payoff_month - plan.payoff_month
                if baseline.payoff_month and plan.payoff_month
                else None
            ),
        }

    scenarios = []
    seen: set[float] = set()
    for step in _scenario_steps(capacity):
        scenarios.append(make_scenario(step))
        seen.add(step)
    # Recommended extra: the user's actual surplus, or their subscription leak if
    # they have no surplus (a behavior-grounded way to fund an extra payment).
    recommended_extra = capacity if capacity > 0 else subscriptions_total
    recommended_extra = round(recommended_extra / 50) * 50 if recommended_extra > 0 else 0.0
    if recommended_extra and recommended_extra not in seen:
        scenarios.append(make_scenario(recommended_extra, "Recomendado: "))
        seen.add(recommended_extra)
    scenarios.sort(key=lambda item: item["extraPayment"])

    avalanche = run(capacity, "avalanche")
    snowball = run(capacity, "snowball")
    chosen = run(recommended_extra)
    payoff_order = _payoff_order(chosen, liabilities, meta)

    high_cost = [
        {"creditor": item.creditor, "apr": _r(item.apr), "balance": _r(item.balance)}
        for item in sorted(liabilities, key=lambda item: (-item.apr, item.id))
    ]
    top = high_cost[0] if high_cost else None
    recommended = next(
        (item for item in scenarios if item["extraPayment"] == recommended_extra),
        scenarios[-1] if scenarios else None,
    )
    if top and capacity <= 0 and subscriptions_total > 0:
        reason = (
            f"Es tu crédito más caro ({top['apr'] * 100:.1f}% anual); redirige "
            f"{_money(subscriptions_total)}/mes de suscripciones para abonarlo."
        )
    elif top:
        reason = f"Es tu crédito más caro ({top['apr'] * 100:.1f}% anual)."
    else:
        reason = "Sin créditos activos."
    next_best = {
        "targetCreditor": top["creditor"] if top else None,
        "extraPayment": recommended["extraPayment"] if recommended else 0.0,
        "interestSaved": recommended["interestSaved"] if recommended else 0.0,
        "monthsSaved": recommended["monthsSaved"] if recommended else None,
        "reason": reason,
    }

    cash_months = (context.get("cashFlow") or {}).get("months") or []
    expense_series = [float(month.get("expenses") or 0) for month in cash_months]
    behavior = {
        "subscriptionLoad": {
            "monthly": subscriptions_total,
            "annual": _r(subscriptions_total * 12),
            "shareOfIncome": _r(subscriptions_total / income) if income else None,
        },
        "expenseVolatility": _r(pstdev(expense_series)) if len(expense_series) > 1 else 0.0,
        "averageSurplus": (
            _r(sum(float(month.get("net") or 0) for month in cash_months) / len(cash_months))
            if cash_months
            else 0.0
        ),
        "categoryTrends": _category_trends(transactions),
    }

    frequency = str((context.get("profile") or {}).get("payFrequency") or "mensual").lower()
    periods = 2 if frequency in ("quincenal", "biweekly", "catorcenal") else 1
    per_inflow = income / periods
    per_outflow = (expenses + min_payment) / periods
    quincena = {
        "periodLabel": "quincena" if periods == 2 else "mes",
        "inflow": _r(per_inflow),
        "outflow": _r(per_outflow),
        "net": _r(per_inflow - per_outflow),
        "tight": (per_inflow - per_outflow) < 0,
    }

    return {
        "currency": "MXN",
        "strategy": strategy,
        "horizonMonths": horizon_months,
        "monthlyIncome": _r(income),
        "monthlyExpenses": _r(expenses),
        "minPayment": min_payment,
        "paymentToIncome": _r(min_payment / income) if income else None,
        "capacity": capacity,
        "baseline": {
            "payoffMonths": baseline.payoff_month,
            "totalInterest": baseline.total_interest,
            "totalPaid": baseline.total_paid,
        },
        "strategies": {
            "avalanche": {"payoffMonths": avalanche.payoff_month, "totalInterest": avalanche.total_interest},
            "snowball": {"payoffMonths": snowball.payoff_month, "totalInterest": snowball.total_interest},
        },
        "scenarios": scenarios,
        "payoffOrder": payoff_order,
        "highCost": high_cost[:3],
        "behavior": behavior,
        "quincena": quincena,
        "nextBestAction": next_best,
    }
