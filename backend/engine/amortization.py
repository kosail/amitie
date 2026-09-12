"""Deterministic debt amortization simulation.

A plan pays the minimum on every liability each month and applies any extra
payment according to a strategy. Interest accrues monthly at `apr / 12`. Cash
accumulates from `net monthly surplus` and can be pushed negative by one-off
`events`, which is what break detection looks for.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping


@dataclass(frozen=True)
class Liability:
    id: str
    creditor: str
    balance: float
    apr: float
    min_payment: float


@dataclass(frozen=True)
class MonthSnapshot:
    month: int
    total_balance: float
    payment: float
    interest: float
    cash: float


@dataclass(frozen=True)
class Plan:
    strategy: str
    months: tuple[MonthSnapshot, ...]
    total_interest: float
    total_paid: float
    payoff_month: int | None
    payoff_months: dict[str, int] = field(default_factory=dict)


def monthly_rate(apr: float) -> float:
    return apr / 12.0


def total_min_payment(liabilities: list[Liability]) -> float:
    return round(sum(liability.min_payment for liability in liabilities), 2)


def _target(liabilities: list[Liability], strategy: str) -> Liability | None:
    active = [liability for liability in liabilities if liability.balance > 0]
    if not active:
        return None
    if strategy == "snowball":
        return min(active, key=lambda liability: (liability.balance, liability.id))
    if strategy == "avalanche":
        return max(active, key=lambda liability: (liability.apr, liability.id))
    return None


def simulate(
    *,
    monthly_income: float,
    monthly_expenses: float,
    liabilities: list[Liability],
    strategy: str = "avalanche",
    horizon_months: int = 36,
    extra_payment: float = 0.0,
    events: Mapping[int, float] | None = None,
    initial_cash: float = 0.0,
) -> Plan:
    events = events or {}
    balances = {liability.id: float(liability.balance) for liability in liabilities}
    cash = float(initial_cash)
    total_interest = 0.0
    total_paid = 0.0
    snapshots: list[MonthSnapshot] = []
    payoff_month: int | None = None
    payoff_months: dict[str, int] = {}

    for month in range(1, horizon_months + 1):
        interest = 0.0
        for liability in liabilities:
            if balances[liability.id] > 0:
                accrued = balances[liability.id] * monthly_rate(liability.apr)
                balances[liability.id] += accrued
                interest += accrued

        current = [replace(liability, balance=balances[liability.id]) for liability in liabilities]
        payments = {
            liability.id: min(liability.min_payment, balances[liability.id])
            for liability in liabilities
        }
        target = _target(current, strategy)
        if target is not None and extra_payment > 0:
            payments[target.id] = min(
                payments[target.id] + extra_payment, balances[target.id]
            )

        debt_payment = 0.0
        for liability in liabilities:
            pay = min(payments[liability.id], balances[liability.id])
            balances[liability.id] = round(max(balances[liability.id] - pay, 0.0), 2)
            debt_payment += pay
            if balances[liability.id] <= 0.01 and liability.id not in payoff_months:
                payoff_months[liability.id] = month

        expenses = monthly_expenses + events.get(month, 0.0)
        cash += monthly_income - expenses - debt_payment
        total_interest += interest
        total_paid += debt_payment

        snapshots.append(
            MonthSnapshot(
                month=month,
                total_balance=round(sum(balances.values()), 2),
                payment=round(debt_payment, 2),
                interest=round(interest, 2),
                cash=round(cash, 2),
            )
        )

        if all(balance <= 0.01 for balance in balances.values()):
            payoff_month = month
            break

    return Plan(
        strategy=strategy,
        months=tuple(snapshots),
        total_interest=round(total_interest, 2),
        total_paid=round(total_paid, 2),
        payoff_month=payoff_month,
        payoff_months=payoff_months,
    )
