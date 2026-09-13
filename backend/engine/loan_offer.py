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


TERM_CANDIDATES = (6, 12, 24, 36, 48)
MIN_TERM = 6
MAX_TERM = 48

# Small loans should not be stretched over long plazos. (ceiling, allowed terms)
AMOUNT_TERM_BANDS: tuple[tuple[float, tuple[int, ...]], ...] = (
    (15_000.0, (6, 12)),
    (50_000.0, (6, 12, 24)),
    (100_000.0, (12, 24, 36)),
)


def allowed_terms_for(amount: float) -> list[int]:
    """The plazos that make sense for this amount (small loans stay short)."""
    for ceiling, terms in AMOUNT_TERM_BANDS:
        if amount < ceiling:
            return list(terms)
    return [12, 24, 36, 48]


def term_options(
    amount: float,
    *,
    apr: float = DEFAULT_APR,
    opening_fee_pct: float = DEFAULT_OPENING_FEE_PCT,
    insurance_fee_pct: float = DEFAULT_INSURANCE_FEE_PCT,
    recommended_months: int | None = None,
    requested_term: int | None = None,
) -> list[dict[str, Any]]:
    """Deterministic plazo options for a fixed principal (loan-term comparison).

    The candidate set is amount-banded (`allowed_terms_for`), always keeping the
    offered/recommended term and any term the user explicitly asked for within
    the product range. Every option is computed by `terms_for` (INV-015).
    """
    if amount <= 0:
        return []
    months_set = set(allowed_terms_for(amount))
    if recommended_months:
        months_set.add(int(recommended_months))
    if requested_term and MIN_TERM <= int(requested_term) <= MAX_TERM:
        months_set.add(int(requested_term))
    options: list[dict[str, Any]] = []
    for months in sorted(months_set):
        terms = terms_for(
            amount,
            apr=apr,
            term_months=months,
            opening_fee_pct=opening_fee_pct,
            insurance_fee_pct=insurance_fee_pct,
        )
        options.append(
            {
                "months": months,
                "label": f"{months} meses",
                "monthlyPayment": terms["monthlyPayment"],
                "totalInterest": terms["totalInterest"],
                "totalCost": terms["totalCost"],
                "cat": terms["cat"],
                "recommended": recommended_months is not None and months == int(recommended_months),
                "requested": requested_term is not None and months == int(requested_term),
            }
        )
    return options


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


# (weight, risk key, reason) — each component's normalized value is in [0, 1].
_RISK_FACTORS: tuple[tuple[float, str, str], ...] = (
    (2.0, "income_cv", "tus ingresos varían mes a mes"),
    (1.0, "expense_cv", "tus gastos cambian mes a mes"),
    (2.0, "low_buffer", "tu colchón de ahorro es menor a un mes de gastos"),
    (2.0, "weak_history", "tu historial de pago reciente"),
    (1.0, "subscription_load", "tus suscripciones pesan en tu ingreso"),
    (1.0, "tight_quincena", "tu quincena queda muy ajustada"),
    (1.0, "savings_delay", "así no retrasas tu meta de ahorro"),
    (2.0, "amount_pressure", "el monto que pediste frente a tu ingreso"),
)


def _risk_components(signals: Mapping[str, Any]) -> dict[str, float]:
    income_cv = float(signals.get("income_cv") or 0.0)
    expense_cv = float(signals.get("expense_cv") or 0.0)
    buffer_months = signals.get("buffer_months")
    on_time = signals.get("on_time_ratio")
    history_available = bool(signals.get("history_available"))
    subscription_share = float(signals.get("subscription_share") or 0.0)
    amount_to_income = float(signals.get("amount_to_income") or 0.0)
    dti_cap = float(signals.get("dti_cap") or DEFAULT_DTI_CAP)
    return {
        "income_cv": _clamp(income_cv / 0.30),
        "expense_cv": _clamp(expense_cv / 0.30),
        "low_buffer": 1.0 if (buffer_months is not None and buffer_months < 1) else 0.0,
        "weak_history": _clamp(1.0 - float(on_time)) if (history_available and on_time is not None) else 0.3,
        "subscription_load": _clamp(subscription_share / 0.15),
        "tight_quincena": 1.0 if signals.get("quincena_tight") else 0.0,
        "savings_delay": 1.0 if signals.get("savings_delay") else 0.0,
        "amount_pressure": _clamp(amount_to_income / dti_cap) if dti_cap > 0 else 0.0,
    }


def _risk_score(signals: Mapping[str, Any]) -> tuple[float, str]:
    """Return `(risk in [0,1], dominant factor's plain-Spanish reason)`."""
    components = _risk_components(signals)
    total_weight = sum(weight for weight, _, _ in _RISK_FACTORS) or 1.0
    score = sum(weight * components[key] for weight, key, _ in _RISK_FACTORS) / total_weight
    _, _, reason = max(_RISK_FACTORS, key=lambda factor: factor[0] * components[factor[1]])
    return _clamp(score), reason


def recommend_term(
    options: Sequence[Mapping[str, Any]],
    *,
    income: float,
    min_payment: float,
    max_payment: float,
    signals: Mapping[str, Any],
) -> dict[str, Any]:
    """Pick the best plazo for this applicant: least interest while affordable.

    A risk-weighted score trades total interest (favored by strong, stable
    profiles) against the monthly burden (favored by volatile income, thin
    liquidity, weak payment history, subscription load, a tight quincena, a
    savings goal at risk, or a large amount relative to income). Only plazos whose
    payment fits the affordable ceiling are eligible.
    """
    if not options:
        return {"months": DEFAULT_TERM_MONTHS, "reason": "", "risk": 0.0}
    risk, factor_reason = _risk_score(signals)
    feasible = [option for option in options if float(option.get("monthlyPayment") or 0.0) <= max_payment + 1e-6]
    if not feasible:
        longest = max(options, key=lambda option: int(option.get("months") or 0))
        return {
            "months": int(longest["months"]),
            "reason": "para que la mensualidad sea lo más baja posible",
            "risk": risk,
        }

    payments = [float(option.get("monthlyPayment") or 0.0) for option in feasible]
    interests = [float(option.get("totalInterest") or 0.0) for option in feasible]
    pay_min, pay_max = min(payments), max(payments)
    int_min, int_max = min(interests), max(interests)
    burden_weight = min(max(0.25 + 0.55 * risk, 0.25), 0.80)
    cost_weight = 1.0 - burden_weight

    best: Mapping[str, Any] | None = None
    best_score = float("inf")
    for option in feasible:
        burden = (float(option.get("monthlyPayment") or 0.0) - pay_min) / (pay_max - pay_min) if pay_max > pay_min else 0.0
        cost = (float(option.get("totalInterest") or 0.0) - int_min) / (int_max - int_min) if int_max > int_min else 0.0
        score = cost_weight * cost + burden_weight * burden
        months = int(option.get("months") or 0)
        if score < best_score - 1e-12 or (
            abs(score - best_score) <= 1e-12 and best is not None and months < int(best.get("months") or 0)
        ):
            best, best_score = option, score
    assert best is not None  # feasible is non-empty
    reason = factor_reason if risk >= 0.20 else "así pagas menos intereses en total"
    return {"months": int(best["months"]), "reason": reason, "risk": round(risk, 3)}


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
    requested_term: int | None = None,
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

    total_balance = round(sum(float(a.get("balance") or 0.0) for a in (accounts or [])), 2)
    buffer_months = round(total_balance / avg_spend, 1) if avg_spend > 0 else None
    worst_existing = max((item.apr for item in liabilities), default=0.0)
    apr_floor = max((float(p.get("aprFloor") or 0.0) for p in (lender_policies or [])), default=0.0)
    income_series = _income_series(context.get("cashFlow") or {})
    cv = round(pstdev(income_series) / mean(income_series), 3) if len(income_series) > 1 and mean(income_series) else 0.0
    expense_series = [
        float(month.get("expenses") or 0.0)
        for month in ((context.get("cashFlow") or {}).get("months") or [])
    ]
    expense_cv = (
        round(pstdev(expense_series) / mean(expense_series), 3)
        if len(expense_series) > 1 and mean(expense_series)
        else 0.0
    )
    periods = 2 if str(profile.get("payFrequency") or "").lower() in ("quincenal", "biweekly", "catorcenal") else 1
    history = _payment_history_impact(payment_history or [])
    baseline_payment = _payment(amount, apr, term_months) if amount > 0 else 0.0
    baseline_savings = _savings_impact(saving_goals or [], surplus_after_base, baseline_payment)

    signals: dict[str, Any] = {
        "income_cv": cv,
        "expense_cv": expense_cv,
        "buffer_months": buffer_months,
        "history_available": bool(history.get("available")),
        "on_time_ratio": history.get("onTimeRatio"),
        "subscription_share": (subscriptions / income) if income else 0.0,
        "quincena_tight": bool(income and (income - avg_spend - min_payment) / periods < 0),
        "savings_delay": bool(baseline_savings and baseline_savings.get("delayedMonths")),
        "amount_to_income": (amount / income) if income else 0.0,
        "dti_cap": dti_cap,
    }

    options = term_options(
        amount,
        apr=apr,
        opening_fee_pct=opening_fee_pct,
        insurance_fee_pct=insurance_fee_pct,
        requested_term=requested_term,
    )
    recommendation = recommend_term(
        options,
        income=income,
        min_payment=min_payment,
        max_payment=max_payment,
        signals=signals,
    )
    engine_months = recommendation["months"] if amount > 0 else term_months
    requested_valid = (
        int(requested_term)
        if requested_term and any(option["months"] == int(requested_term) for option in options)
        else None
    )
    selected_months = requested_valid or engine_months
    for option in options:
        option["recommended"] = option["months"] == selected_months
        option["requested"] = requested_valid is not None and option["months"] == requested_valid
        if option["recommended"]:
            option["reason"] = (
                recommendation["reason"]
                if selected_months == engine_months
                else "es el plazo que pediste"
            )

    # The offer is presented at the selected plazo: the term the user asked for
    # when they gave one, otherwise the engine recommendation.
    term_months = selected_months
    payment = round(_payment(amount, apr, term_months), 2) if amount > 0 else 0.0
    schedule = _schedule(amount, apr, term_months) if amount > 0 else []
    opening_fee = round(amount * opening_fee_pct, 2)
    insurance_fee = round(amount * insurance_fee_pct, 2)
    total_interest = round(sum(row["interest"] for row in schedule), 2)
    total_cost = round(sum(row["payment"] for row in schedule) + opening_fee + insurance_fee, 2)
    cat = compute_cat(amount, apr, term_months, opening_fee, insurance_fee)
    dti_with = round((min_payment + payment) / income, 4) if income else None
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
        "options": options,
        "recommendation": {
            "months": selected_months,
            "engineRecommended": engine_months,
            "requested": requested_valid,
            "reason": recommendation["reason"],
            "risk": recommendation["risk"],
            "text": (
                f"Recomendamos {engine_months} meses"
                + (f": {recommendation['reason']}." if recommendation.get("reason") else ".")
                if selected_months == engine_months
                else f"Elegiste {selected_months} meses."
            ),
        },
        "capacity": {
            "income": _r(income),
            "minPayment": min_payment,
            "maxPayment": _r(max_payment),
            "dtiCap": dti_cap,
        },
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
