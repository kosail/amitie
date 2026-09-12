"""Finance reads: DB rows -> domain dicts.

`financial_context()` is the canonical shape shared by generation and
hydration, so a re-hydrated surface always mirrors what the agent generated,
with fresh values.
"""

from __future__ import annotations

from typing import Any

from db.port import DatabasePort
from engine import offer as offer_engine
from engine import planning


async def get_profile(database: DatabasePort, user_id: str) -> dict[str, Any] | None:
    row = await database.fetch_one(
        "SELECT u.id, u.name, u.age, u.city, u.monthly_income, u.pay_frequency, u.credit_score, "
        "a.mode AS accessibility_mode "
        "FROM users u LEFT JOIN accessibility_profiles a ON a.user_id = u.id WHERE u.id = ?",
        (user_id,),
    )
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "age": row["age"],
        "city": row["city"],
        "monthlyIncome": row["monthly_income"],
        "payFrequency": row["pay_frequency"],
        "creditScore": row["credit_score"],
        "accessibilityMode": row["accessibility_mode"],
    }


async def get_liabilities(database: DatabasePort, user_id: str) -> list[dict[str, Any]]:
    rows = await database.fetch_all(
        "SELECT id, creditor, kind, principal, balance, apr, min_payment, due_day, "
        "nomina_discount, status FROM liabilities WHERE user_id = ? "
        "ORDER BY balance DESC, id ASC",
        (user_id,),
    )
    return [
        {
            "id": row["id"],
            "creditor": row["creditor"],
            "kind": row["kind"],
            "principal": row["principal"],
            "balance": row["balance"],
            "apr": row["apr"],
            "minPayment": row["min_payment"],
            "dueDay": row["due_day"],
            "nominaDiscount": row["nomina_discount"],
            "status": row["status"],
        }
        for row in rows
    ]


async def get_income_streams(database: DatabasePort, user_id: str) -> list[dict[str, Any]]:
    rows = await database.fetch_all(
        "SELECT id, source, amount, frequency, next_date FROM income_streams WHERE user_id = ? "
        "ORDER BY amount DESC, id ASC",
        (user_id,),
    )
    return [
        {
            "id": row["id"],
            "source": row["source"],
            "amount": row["amount"],
            "frequency": row["frequency"],
            "nextDate": row["next_date"],
        }
        for row in rows
    ]


async def get_subscriptions(database: DatabasePort, user_id: str) -> list[dict[str, Any]]:
    rows = await database.fetch_all(
        "SELECT id, merchant, amount, period, next_charge FROM subscriptions WHERE user_id = ? "
        "ORDER BY amount DESC, id ASC",
        (user_id,),
    )
    return [
        {
            "id": row["id"],
            "merchant": row["merchant"],
            "amount": row["amount"],
            "period": row["period"],
            "nextCharge": row["next_charge"],
        }
        for row in rows
    ]


async def get_cash_flow(
    database: DatabasePort, user_id: str, months: int = 6
) -> dict[str, Any]:
    rows = await database.fetch_all(
        "SELECT substr(occurred_on, 1, 7) AS period, "
        "SUM(CASE WHEN direction = 'in' THEN amount ELSE 0 END) AS income, "
        "SUM(CASE WHEN direction = 'out' THEN amount ELSE 0 END) AS expenses "
        "FROM transactions WHERE user_id = ? GROUP BY period ORDER BY period DESC LIMIT ?",
        (user_id, months),
    )
    entries = [
        {
            "period": row["period"],
            "income": round(row["income"], 2),
            "expenses": round(row["expenses"], 2),
            "net": round(row["income"] - row["expenses"], 2),
        }
        for row in reversed(list(rows))
    ]
    average = round(sum(entry["net"] for entry in entries) / len(entries), 2) if entries else 0.0
    return {"months": entries, "averageSurplus": average}


async def financial_context(database: DatabasePort, user_id: str) -> dict[str, Any]:
    profile = await get_profile(database, user_id)
    liabilities = await get_liabilities(database, user_id)
    income_streams = await get_income_streams(database, user_id)
    subscriptions = await get_subscriptions(database, user_id)
    cash_flow = await get_cash_flow(database, user_id)
    return {
        "profile": profile,
        "liabilities": liabilities,
        "totals": {
            "debt": round(sum(item["balance"] for item in liabilities), 2),
            "minPayment": round(sum(item["minPayment"] for item in liabilities), 2),
        },
        "incomeStreams": income_streams,
        "subscriptions": subscriptions,
        "subscriptionTotal": round(sum(item["amount"] for item in subscriptions), 2),
        "cashFlow": cash_flow,
    }


async def simulate_plan(
    database: DatabasePort,
    user_id: str,
    *,
    strategy: str = planning.DEFAULT_STRATEGY,
    extra_payment: float = 0.0,
    extra_income: float = 0.0,
    expense_reduction: float = 0.0,
    horizon_months: int = 36,
    events: dict[str, float] | None = None,
) -> dict[str, Any]:
    context = await financial_context(database, user_id)
    plan = planning.run_simulation(
        context,
        strategy=strategy,
        extra_payment=extra_payment,
        extra_income=extra_income,
        expense_reduction=expense_reduction,
        horizon_months=horizon_months,
        events=events,
    )
    return {
        "plan": planning.plan_payload(plan),
        "break": planning.break_payload(plan),
        "inputs": planning.simulation_inputs(context),
    }


async def detect_plan_breaks(
    database: DatabasePort,
    user_id: str,
    *,
    strategy: str = planning.DEFAULT_STRATEGY,
    extra_payment: float = 0.0,
    extra_income: float = 0.0,
    expense_reduction: float = 0.0,
    horizon_months: int = 36,
    events: dict[str, float] | None = None,
) -> dict[str, Any]:
    context = await financial_context(database, user_id)
    plan = planning.run_simulation(
        context,
        strategy=strategy,
        extra_payment=extra_payment,
        extra_income=extra_income,
        expense_reduction=expense_reduction,
        horizon_months=horizon_months,
        events=events,
    )
    breakdown = planning.break_payload(plan)
    return {
        "break": breakdown,
        "breakMonth": breakdown["month"] if breakdown else None,
        "shortfall": breakdown["shortfall"] if breakdown else 0.0,
    }


async def get_lender_policies(database: DatabasePort) -> dict[str, Any]:
    rows = await database.fetch_all(
        "SELECT id, creditor, strategy, min_settlement_pct, max_months, apr_floor, "
        "accepts_consolidation FROM lender_policies ORDER BY creditor, strategy"
    )
    return {
        "policies": [
            {
                "id": row["id"],
                "creditor": row["creditor"],
                "strategy": row["strategy"],
                "minSettlementPct": row["min_settlement_pct"],
                "maxMonths": row["max_months"],
                "aprFloor": row["apr_floor"],
                "acceptsConsolidation": bool(row["accepts_consolidation"]),
            }
            for row in rows
        ]
    }


async def generate_offer(
    database: DatabasePort,
    user_id: str,
    *,
    creditor: str | None = None,
    strategy: str = "consolidation",
) -> dict[str, Any]:
    context = await financial_context(database, user_id)
    policies = (await get_lender_policies(database))["policies"]
    return offer_engine.generate_offer(context, policies, creditor=creditor, strategy=strategy)


async def evaluate_offer(
    database: DatabasePort, user_id: str, offer: dict[str, Any]
) -> dict[str, Any]:
    context = await financial_context(database, user_id)
    return offer_engine.evaluate_offer(context, offer)


async def accept_offer(
    database: DatabasePort, user_id: str, offer: dict[str, Any]
) -> dict[str, Any]:
    return {
        "status": "ok",
        "offer": offer,
        "nextSteps": [
            "Firma el convenio digital",
            "Revisa tu primer pago en la app",
        ],
    }
