"""Deterministic offer generation and evaluation (INV-015).

Lender policies bound what the bank persona may offer; the engine computes every
number. Evaluation models the offer as a single consolidated liability and runs
the same simulation used elsewhere.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import planning

_STRATEGY_ALIASES = {
    "consolidation": ("consolidation", "restructure"),
    "restructure": ("restructure", "consolidation"),
    "settlement": ("settlement",),
}


def weighted_apr(liabilities: list[Any]) -> float:
    total = sum(liability.balance for liability in liabilities)
    if total <= 0:
        return 0.0
    weighted = sum(liability.balance * liability.apr for liability in liabilities)
    return weighted / total


def _amortized_payment(principal: float, apr: float, months: int) -> float:
    if months <= 0:
        return principal
    rate = apr / 12.0
    if rate <= 0:
        return principal / months
    return principal * rate / (1 - (1 + rate) ** (-months))


def choose_policy(
    policies: list[Mapping[str, Any]], *, creditor: str | None = None, strategy: str = "consolidation"
) -> Mapping[str, Any] | None:
    aliases = _STRATEGY_ALIASES.get(strategy, (strategy,))
    candidates = [policy for policy in policies if policy.get("strategy") in aliases]
    if creditor:
        for policy in candidates:
            if policy.get("creditor") == creditor:
                return policy
    if candidates:
        return candidates[0]
    return policies[0] if policies else None


def generate_offer(
    context: Mapping[str, Any],
    policies: list[Mapping[str, Any]],
    *,
    creditor: str | None = None,
    strategy: str = "consolidation",
) -> dict[str, Any]:
    liabilities = planning.liabilities_from_context(context)
    debt = round(sum(liability.balance for liability in liabilities), 2)
    policy = choose_policy(policies, creditor=creditor, strategy=strategy)
    if policy is None:
        return {"status": "error", "issues": ["no lender policies available"]}

    months = int(policy["maxMonths"])
    if strategy == "settlement":
        principal = round(debt * float(policy["minSettlementPct"]), 2)
        apr = float(policy["aprFloor"])
    else:
        principal = debt
        apr = round(max(weighted_apr(liabilities), float(policy["aprFloor"])), 4)

    payment = round(_amortized_payment(principal, apr, months), 2)
    return {
        "status": "ok",
        "offer": {
            "creditor": policy["creditor"],
            "strategy": strategy,
            "principal": principal,
            "apr": apr,
            "months": months,
            "monthlyPayment": payment,
            "totalCost": round(payment * months, 2),
            "settlementPct": float(policy["minSettlementPct"]),
        },
        "bounds": {
            "aprFloor": float(policy["aprFloor"]),
            "maxMonths": int(policy["maxMonths"]),
            "minSettlementPct": float(policy["minSettlementPct"]),
        },
    }


def evaluate_offer(
    context: Mapping[str, Any], offer: Mapping[str, Any], *, horizon_months: int = 36
) -> dict[str, Any]:
    plan = planning.run_simulation(context, offer=offer, horizon_months=horizon_months)
    breakdown = planning.break_payload(plan)
    return {
        "feasible": breakdown is None,
        "break": breakdown,
        "monthlyPayment": float(offer.get("monthlyPayment") or 0.0),
        "payoffMonth": plan.payoff_month,
        "totalPaid": plan.total_paid,
    }
