"""Saving-bag estimation and feasibility (INV-015).

Pure functions only. The agent decides the questions and the goal; this module
turns a research snapshot plus the user's answers into a deterministic cost
estimate, and the user's financial context into a dated funding plan.
"""

from __future__ import annotations

import calendar
import math
from datetime import date
from typing import Any, Mapping

from . import feasibility as feasibility_engine
from . import planning

STYLE_MULTIPLIERS: dict[str, float] = {
    "mochilero": 0.8,
    "economico": 0.85,
    "económico": 0.85,
    "estandar": 1.0,
    "estándar": 1.0,
    "confort": 1.3,
    "lujo": 1.8,
    "premium": 1.8,
}
DEFAULT_STYLE_MULTIPLIER = 1.0
CONTINGENCY_RATE = 0.10

_COST_KEYS = {
    "flight": ("flight_roundtrip_mxn", "flightRoundtripMxn", "flight"),
    "lodging": ("lodging_per_night_mxn", "lodgingPerNightMxn", "lodging"),
    "food": ("food_per_day_mxn", "foodPerDayMxn", "food"),
    "transport": ("transport_per_day_mxn", "transportPerDayMxn", "transport"),
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _answer(answers: Mapping[str, Any] | None, key: str, default: Any = None) -> Any:
    if not answers:
        return default
    if key in answers:
        return answers[key]
    for candidate, value in answers.items():
        if str(candidate).lower() == key.lower():
            return value
    return default


def _cost(research: Mapping[str, Any], kind: str, default: float = 0.0) -> float:
    for key in _COST_KEYS[kind]:
        if key in research:
            return _as_float(research[key], default)
    return default


def style_multiplier(style: Any) -> float:
    if style is None:
        return DEFAULT_STYLE_MULTIPLIER
    return STYLE_MULTIPLIERS.get(str(style).strip().lower(), DEFAULT_STYLE_MULTIPLIER)


def estimate_total(
    research: Mapping[str, Any] | None, answers: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Deterministically estimate a trip/goal cost from research + answers."""
    research = research or {}
    days = max(_as_int(_answer(answers, "days", _answer(answers, "duration", 7)), 7), 1)
    travelers = max(_as_int(_answer(answers, "travelers", _answer(answers, "people", 1)), 1), 1)
    nights = max(days - 1, 1)
    rooms = max(1, math.ceil(travelers / 2))
    multiplier = style_multiplier(_answer(answers, "style"))

    flights = round(_cost(research, "flight") * travelers, 2)
    lodging = round(_cost(research, "lodging") * nights * rooms, 2)
    food = round(_cost(research, "food") * days * travelers, 2)
    transport = round(_cost(research, "transport") * days * travelers, 2)
    subtotal = round((flights + lodging + food + transport) * multiplier, 2)
    contingency = round(subtotal * CONTINGENCY_RATE, 2)
    total = round(subtotal + contingency, 2)

    return {
        "estimatedTotal": total,
        "currency": "MXN",
        "breakdown": {
            "flights": flights,
            "lodging": lodging,
            "food": food,
            "transport": transport,
            "contingency": contingency,
        },
        "inputs": {
            "days": days,
            "nights": nights,
            "travelers": travelers,
            "rooms": rooms,
            "styleMultiplier": multiplier,
        },
    }


def goal_gap(target_amount: Any, estimated_total: float) -> dict[str, Any]:
    """Compare the researched estimate against the user's declared goal (REQ-BAG-06)."""
    target = _as_float(target_amount, 0.0)
    gap = round(estimated_total - target, 2)
    if gap > 0:
        status = "over"
    elif gap < 0:
        status = "under"
    else:
        status = "on_target"
    return {"target": target, "estimatedTotal": estimated_total, "gap": gap, "status": status}


def financial_capacity(context: Mapping[str, Any]) -> float:
    inputs = planning.simulation_inputs(context)
    return feasibility_engine.available_monthly_capacity(
        inputs["monthlyIncome"], inputs["monthlyExpenses"], inputs["minPayment"]
    )


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _add_months(start: date, months: int) -> date:
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, _days_in_month(year, month))
    return date(year, month, day)


def months_until(target_date: Any, today: date) -> int:
    if not target_date:
        return 12
    try:
        target = date.fromisoformat(str(target_date)[:10])
    except ValueError:
        return 12
    if target <= today:
        return 0
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if target.day > today.day:
        months += 1
    return max(months, 1)


def build_savings_plan(
    context: Mapping[str, Any],
    bag: Mapping[str, Any],
    research: Mapping[str, Any] | None,
    answers: Mapping[str, Any] | None = None,
    *,
    current_saved: float = 0.0,
    today: date | None = None,
    goal_reduced: bool = False,
) -> dict[str, Any]:
    """Compose the full deterministic funding plan for a saving bag."""
    today = today or date.today()
    estimate = estimate_total(research, answers)
    capacity = financial_capacity(context)
    available = months_until(bag.get("target_date"), today)
    feasibility = feasibility_engine.compute_feasibility(
        target_amount=estimate["estimatedTotal"],
        current_saved=max(_as_float(current_saved), 0.0),
        monthly_capacity=capacity,
        months_available=available,
    )
    projected = (
        _add_months(today, feasibility.months_needed).isoformat()
        if feasibility.months_needed is not None
        else None
    )
    if capacity <= 0:
        status = "off_track"
    elif feasibility.on_time:
        status = "on_track"
    else:
        status = "at_risk"

    funded = round(max(current_saved, 0.0) + max(capacity, 0.0) * available, 2)
    shortfall = round(max(estimate["estimatedTotal"] - funded, 0.0), 2)
    plan = {
        "estimatedTotal": estimate["estimatedTotal"],
        "currency": "MXN",
        "monthlyCapacity": capacity,
        "monthsAvailable": available,
        "monthsNeeded": feasibility.months_needed,
        "projectedDate": projected,
        "onTime": feasibility.on_time,
        "feasibility": status,
        "fundedTarget": funded,
        "shortfall": shortfall,
        "currentSaved": round(max(_as_float(current_saved), 0.0), 2),
        "goal": goal_gap(bag.get("target_amount"), estimate["estimatedTotal"]),
        "breakdown": estimate["breakdown"],
        "inputs": estimate["inputs"],
    }
    plan["redirect"] = suggest_redirect(plan, goal_reduced=goal_reduced)
    return plan


def suggest_redirect(
    plan: Mapping[str, Any], *, goal_reduced: bool = False
) -> dict[str, Any]:
    """Recommend a loan handoff into La Mesa when the bag cannot be funded in time."""
    shortfall = _as_float(plan.get("shortfall"), 0.0)
    status = str(plan.get("feasibility") or "")
    recommended = status in ("at_risk", "off_track") and shortfall > 0
    if goal_reduced and recommended:
        reason = "goal_reduction"
    elif status == "off_track":
        reason = "no_capacity"
    elif recommended:
        reason = "deadline"
    else:
        reason = "on_track"
    return {
        "recommended": recommended,
        "amount": round(shortfall, 2) if recommended else 0.0,
        "reason": reason,
    }
