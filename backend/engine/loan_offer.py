"""Deterministic loan offer + risk framework (INV-015).

Given the user's real financial context (plus accounts, lender policies, saving
goals and payment history), this computes the loan the bank should offer — amount
derived from affordability, terms, an IRR-based CAT, and a full risk panel
(DTI, disposable surplus, liquidity buffer, relative cost, income stability,
payroll deduction, savings-goal impact, payment-history score projection).
The LLM only presents these numbers; it never computes them.
"""

from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

from . import feasibility, planning

DEFAULT_APR = 0.24
DEFAULT_TERM_MONTHS = 24
DEFAULT_DTI_CAP = 0.35
DEFAULT_OPENING_FEE_PCT = 0.02
DEFAULT_INSURANCE_FEE_PCT = 0.01


def _r(value: Any) -> float:
    return round(float(value), 2)


def _period_months(period: Any) -> float:
    p = str(period or "mensual").lower()
    if p in ("anual", "annual", "yearly"):
        return 1.0 / 12.0
    if p in ("trimestral", "quarterly"):
        return 1.0 / 3.0
    if p in ("quincenal", "biweekly", "catorcenal"):
        return 2.0
    return 1.0


def _payment(principal: float, apr: float, months: int) -> float:
    if months <= 0:
        return principal
    rate = apr / 12.0
    if rate <= 0:
        return principal / months
    return principal * rate / (1 - (1 + rate) ** (-months))


def _principal_for_payment(payment: float, apr: float, months: int) -> float:
    if months <= 0 or payment <= 0:
        return 0.0
    rate = apr / 12.0
    if rate <= 0:
        return payment * months
    return payment * (1 - (1 + rate) ** (-months)) / rate


def _schedule(principal: float, apr: float, months: int) -> list[dict[str, Any]]:
    rate = apr / 12.0
    balance = principal
    rows: list[dict[str, Any]] = []
    for month in range(1, months + 1):
        interest = round(balance * rate, 2)
        due = _payment(principal, apr, months)
        pay = round(min(due, balance + interest), 2)
        principal_part = round(pay - interest, 2)
        balance = round(max(balance - principal_part, 0.0), 2)
        rows.append(
            {
                "month": month,
                "payment": pay,
                "interest": interest,
                "principal": principal_part,
                "balance": balance,
            }
        )
    return rows


def _monthly_subscriptions(subscriptions: Sequence[Mapping[str, Any]]) -> float:
    return round(sum(float(s.get("amount") or 0) * _period_months(s.get("period")) for s in subscriptions), 2)


def _monthly_spend(cash_flow: Mapping[str, Any]) -> float:
    months = (cash_flow or {}).get("months") or []
    if not months:
        return 0.0
    return round(mean(float(m.get("expenses") or 0.0) for m in months), 2)


def _income_series(cash_flow: Mapping[str, Any]) -> list[float]:
    return [float(m.get("income") or 0.0) for m in ((cash_flow or {}).get("months") or [])]


def compute_cat(
    amount: float,
    apr: float,
    term_months: int,
    opening_fee: float,
    insurance_fee: float,
) -> float:
    """IRR-based annualized cost (approximate CAT) including fees/insurance."""
    net_received = amount - opening_fee - insurance_fee
    if amount <= 0 or term_months <= 0 or net_received <= 0:
        return 0.0
    payment = _payment(amount, apr, term_months)

    def pv(rate: float) -> float:
        if rate <= 0:
            return payment * term_months - net_received
        return payment * (1 - (1 + rate) ** (-term_months)) / rate - net_received

    lo, hi = 0.0, 1.0
    if pv(lo) <= 0:
        return 0.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if pv(mid) > 0:
            lo = mid
        else:
            hi = mid
    monthly_rate = (lo + hi) / 2.0
    return round(monthly_rate * 12.0, 4)


def _savings_impact(
    saving_goals: Sequence[Mapping[str, Any]], surplus_before: float, new_payment: float
) -> dict[str, Any] | None:
    if not saving_goals:
        return None
    goal = saving_goals[0]
    target = float(goal.get("targetAmount") or goal.get("target_amount") or 0.0)
    saved = float(goal.get("currentSaved") or goal.get("current_saved") or 0.0)
    if target <= 0:
        return None
    after = surplus_before - new_payment
    months_before = feasibility.project_completion(target, max(surplus_before, 0.0), saved)
    months_after = feasibility.project_completion(target, after, saved) if after > 0 else None
    if months_before is None and months_after is None:
        return None
    delay = None
    if months_before is not None and months_after is not None:
        delay = months_after - months_before
    return {
        "goal": goal.get("name"),
        "monthsBefore": months_before,
        "monthsAfter": months_after,
        "delayedMonths": delay,
    }


def _payment_history_impact(history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(history)
    if total == 0:
        return {"available": False, "onTimeRatio": None, "projectedScoreDelta": 0}
    on_time = sum(1 for h in history if str(h.get("status")) == "on_time")
    late = sum(1 for h in history if str(h.get("status")) == "late")
    missed = total - on_time - late
    ratio = round(on_time / total, 2)
    delta = 0
    if ratio >= 0.95:
        delta = 8
    elif ratio >= 0.8:
        delta = 2
    else:
        delta = -6 - 4 * missed
    return {
        "available": True,
        "onTimeRatio": ratio,
        "late": late,
        "missed": missed,
        "projectedScoreDelta": delta,
    }


def terms_for(
    amount: float,
    *,
    apr: float = DEFAULT_APR,
    term_months: int = DEFAULT_TERM_MONTHS,
    opening_fee_pct: float = DEFAULT_OPENING_FEE_PCT,
    insurance_fee_pct: float = DEFAULT_INSURANCE_FEE_PCT,
) -> dict[str, Any]:
    """Deterministic terms + schedule for an exact principal (used on accept)."""
    payment = round(_payment(amount, apr, term_months), 2) if amount > 0 else 0.0
    schedule = _schedule(amount, apr, term_months) if amount > 0 else []
    opening_fee = round(amount * opening_fee_pct, 2)
    insurance_fee = round(amount * insurance_fee_pct, 2)
    return {
        "amount": _r(amount),
        "apr": round(apr, 4),
        "termMonths": term_months,
        "openingFee": opening_fee,
        "insuranceFee": insurance_fee,
        "cat": compute_cat(amount, apr, term_months, opening_fee, insurance_fee),
        "monthlyPayment": payment,
        "totalInterest": round(sum(row["interest"] for row in schedule), 2),
        "totalCost": round(sum(row["payment"] for row in schedule) + opening_fee + insurance_fee, 2),
        "schedule": schedule,
    }


def propose_offer(
    context: Mapping[str, Any],
    *,
    accounts: Sequence[Mapping[str, Any]] | None = None,
    lender_policies: Sequence[Mapping[str, Any]] | None = None,
    saving_goals: Sequence[Mapping[str, Any]] | None = None,
    payment_history: Sequence[Mapping[str, Any]] | None = None,
    requested_amount: float | None = None,
    apr: float = DEFAULT_APR,
    term_months: int = DEFAULT_TERM_MONTHS,
    opening_fee_pct: float = DEFAULT_OPENING_FEE_PCT,
    insurance_fee_pct: float = DEFAULT_INSURANCE_FEE_PCT,
    dti_cap: float = DEFAULT_DTI_CAP,
    payroll_deduction: bool = False,
) -> dict[str, Any]:
    profile = context.get("profile") or {}
    income = float(profile.get("monthlyIncome") or 0.0)
    liabilities = planning.liabilities_from_context(context)
    min_payment = round(sum(item.min_payment for item in liabilities), 2)
    subscriptions = _monthly_subscriptions(context.get("subscriptions") or [])
    avg_spend = _monthly_spend(context.get("cashFlow") or {})
    avg_discretionary = max(avg_spend - subscriptions, 0.0)
    surplus = round(income - subscriptions - min_payment - avg_discretionary, 2)

    # Amount: keep DTI <= cap and the payment within the actual surplus.
    surplus_after_base = max(income - min_payment - avg_spend, 0.0)
    max_payment = max(0.0, min(income * dti_cap - min_payment, surplus_after_base))
    max_principal = _principal_for_payment(max_payment, apr, term_months)
    if requested_amount is not None and requested_amount > 0:
        amount = min(float(requested_amount), max_principal)
    else:
        amount = max_principal
    amount = math.floor(max(amount, 0.0) / 500.0) * 500.0

    payment = round(_payment(amount, apr, term_months), 2) if amount > 0 else 0.0
    schedule = _schedule(amount, apr, term_months) if amount > 0 else []
    opening_fee = round(amount * opening_fee_pct, 2)
    insurance_fee = round(amount * insurance_fee_pct, 2)
    total_interest = round(sum(row["interest"] for row in schedule), 2)
    total_cost = round(sum(row["payment"] for row in schedule) + opening_fee + insurance_fee, 2)
    cat = compute_cat(amount, apr, term_months, opening_fee, insurance_fee)

    total_balance = round(sum(float(a.get("balance") or 0.0) for a in (accounts or [])), 2)
    buffer_months = round(total_balance / avg_spend, 1) if avg_spend > 0 else None
    dti_with = round((min_payment + payment) / income, 4) if income else None
    worst_existing = max((item.apr for item in liabilities), default=0.0)
    apr_floor = max((float(p.get("aprFloor") or 0.0) for p in (lender_policies or [])), default=0.0)
    income_series = _income_series(context.get("cashFlow") or {})
    cv = round(pstdev(income_series) / mean(income_series), 3) if len(income_series) > 1 and mean(income_series) else 0.0
    savings_impact = _savings_impact(saving_goals or [], surplus_after_base, payment)

    warnings: list[str] = []
    if dti_with is not None and dti_with > dti_cap:
        warnings.append(
            f"Tu capacidad de pago quedaría en {dti_with * 100:.0f}% del ingreso (arriba del {dti_cap * 100:.0f}%)."
        )
    if buffer_months is not None and buffer_months < 1:
        warnings.append("Tu colchón de liquidez es menor a un mes de gastos.")
    if amount > 0 and worst_existing > 0 and apr > worst_existing:
        warnings.append(
            f"La tasa ofrecida ({apr * 100:.1f}%) es mayor que tu deuda más cara ({worst_existing * 100:.1f}%)."
        )
    if cv > 0.15:
        warnings.append("Tus ingresos son variables mes a mes; un pago fijo es más riesgoso.")
    if savings_impact and savings_impact.get("delayedMonths"):
        warnings.append(
            f"Este crédito retrasaría tu meta '{savings_impact['goal']}' {savings_impact['delayedMonths']} meses."
        )
    if amount <= 0:
        warnings.append("Con tu ingreso y gastos actuales no hay margen para un crédito.")

    periods = 2 if str(profile.get("payFrequency") or "").lower() in ("quincenal", "biweekly", "catorcenal") else 1
    net_per_period = round((income - payment) / periods, 2) if payroll_deduction else None

    return {
        "currency": "MXN",
        "offer": {
            "amount": _r(amount),
            "apr": round(apr, 4),
            "termMonths": term_months,
            "openingFee": opening_fee,
            "insuranceFee": insurance_fee,
            "cat": cat,
            "monthlyPayment": payment,
            "totalInterest": total_interest,
            "totalCost": total_cost,
        },
        "schedule": schedule,
        "risk": {
            "dti": {"existing": _r(min_payment / income) if income else None, "withOffer": dti_with, "cap": dti_cap, "flag": bool(dti_with and dti_with > dti_cap)},
            "surplus": {"monthly": surplus, "discretionarySpend": _r(avg_discretionary), "subscriptions": subscriptions, "minPayment": min_payment},
            "liquidityBufferMonths": buffer_months,
            "relativeCost": {"offeredApr": round(apr, 4), "worstExistingApr": round(worst_existing, 4), "aprFloor": round(apr_floor, 4), "worse": bool(worst_existing and apr > worst_existing)},
            "incomeStability": {"coefficientOfVariation": cv, "flag": cv > 0.15},
            "payrollDeduction": {"applied": payroll_deduction, "netPerPeriod": net_per_period},
            "savingsImpact": savings_impact,
            "paymentHistory": _payment_history_impact(payment_history or []),
        },
        "affordable": amount > 0 and (dti_with is None or dti_with <= dti_cap),
        "warnings": warnings,
    }
