"""Finance reads: DB rows -> domain dicts.

`financial_context()` is the canonical shape shared by generation and
hydration, so a re-hydrated surface always mirrors what the agent generated,
with fresh values.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from db.port import DatabasePort
from engine import loan_offer
from engine import loans_analysis
from engine import offer as offer_engine
from engine import planning

from .clabe import is_valid_clabe


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payment_id() -> str:
    return "txn_" + uuid.uuid4().hex[:10]


def _recipient_id() -> str:
    return "rcpt_" + uuid.uuid4().hex[:10]


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


def _liability_row(row: Any) -> dict[str, Any]:
    return {
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


async def get_accounts(database: DatabasePort, user_id: str) -> list[dict[str, Any]]:
    rows = await database.fetch_all(
        "SELECT id, user_id, kind, institution, balance, currency FROM accounts "
        "WHERE user_id = ? ORDER BY kind ASC, id ASC",
        (user_id,),
    )
    return [
        {
            "id": row["id"],
            "userId": row["user_id"],
            "kind": row["kind"],
            "institution": row["institution"],
            "balance": row["balance"],
            "currency": row["currency"],
        }
        for row in rows
    ]


async def make_payment(
    database: DatabasePort,
    user_id: str,
    liability_id: str,
    amount: float,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Apply an extra/regular payment ("abono") to a liability.

    Deterministic and idempotent-safe: validates funds, moves money out of the
    funding account, reduces the liability balance, and records a transaction
    row, all in a single batch write (INV-015: the LLM never touches this math).
    """
    if amount is None or amount <= 0:
        return {"status": "error", "issues": ["El monto debe ser mayor a cero."]}

    liability_row = await database.fetch_one(
        "SELECT id, creditor, kind, principal, balance, apr, min_payment, due_day, "
        "nomina_discount, status FROM liabilities WHERE id = ? AND user_id = ?",
        (liability_id, user_id),
    )
    if liability_row is None:
        return {"status": "error", "issues": ["No se encontró ese préstamo."]}
    if liability_row["status"] != "active":
        return {"status": "error", "issues": ["Este préstamo ya no está activo."]}

    if account_id:
        account_row = await database.fetch_one(
            "SELECT id, user_id, kind, institution, balance, currency FROM accounts "
            "WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        )
    else:
        account_row = await database.fetch_one(
            "SELECT id, user_id, kind, institution, balance, currency FROM accounts "
            "WHERE user_id = ? ORDER BY (kind = 'checking') DESC, balance DESC LIMIT 1",
            (user_id,),
        )
    if account_row is None:
        return {"status": "error", "issues": ["No se encontró una cuenta de origen."]}
    if account_row["balance"] < amount:
        return {"status": "error", "issues": ["Fondos insuficientes en la cuenta de origen."]}

    applied = round(min(amount, liability_row["balance"]), 2)
    new_liability_balance = round(liability_row["balance"] - applied, 2)
    new_status = "paid" if new_liability_balance <= 0.01 else liability_row["status"]
    new_account_balance = round(account_row["balance"] - amount, 2)

    payment_id = _payment_id()
    occurred_on = date.today().isoformat()

    await database.batch(
        [
            (
                "UPDATE liabilities SET balance = ?, status = ? WHERE id = ?",
                (new_liability_balance, new_status, liability_id),
            ),
            (
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (new_account_balance, account_row["id"]),
            ),
            (
                "INSERT INTO transactions (id, user_id, account_id, occurred_on, amount, "
                "direction, category, merchant, is_subscription) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    payment_id,
                    user_id,
                    account_row["id"],
                    occurred_on,
                    applied,
                    "out",
                    "debt_payment",
                    liability_row["creditor"],
                    0,
                ),
            ),
        ]
    )

    updated_liability = dict(liability_row)
    updated_liability["balance"] = new_liability_balance
    updated_liability["status"] = new_status

    return {
        "status": "ok",
        "appliedAmount": applied,
        "liability": _liability_row(updated_liability),
        "account": {
            "id": account_row["id"],
            "userId": account_row["user_id"],
            "kind": account_row["kind"],
            "institution": account_row["institution"],
            "balance": new_account_balance,
            "currency": account_row["currency"],
        },
        "transaction": {
            "id": payment_id,
            "accountId": account_row["id"],
            "occurredOn": occurred_on,
            "amount": applied,
            "direction": "out",
            "category": "debt_payment",
            "merchant": liability_row["creditor"],
        },
    }


def _recipient_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "alias": row["alias"],
        "clabe": row["clabe"],
        "bankName": row["bank_name"],
        "createdAt": row["created_at"],
    }


async def list_recipients(database: DatabasePort, user_id: str) -> list[dict[str, Any]]:
    rows = await database.fetch_all(
        "SELECT id, alias, clabe, bank_name, created_at FROM saved_recipients "
        "WHERE user_id = ? ORDER BY created_at DESC, id ASC",
        (user_id,),
    )
    return [_recipient_row(row) for row in rows]


async def create_recipient(
    database: DatabasePort, user_id: str, alias: str, clabe: str, bank_name: str
) -> dict[str, Any]:
    """Save a new recipient (CLABE + bank + alias) for future transfers.

    Re-validates the CLABE checksum server-side (INV-015: never trust the
    client alone for a money-adjacent field), mirroring the frontend's
    `src/features/transfers/clabe.ts` algorithm exactly (`.clabe` module).
    """
    if not alias or not alias.strip():
        return {"status": "error", "issues": ["El alias no puede estar vacío."]}
    if not is_valid_clabe(clabe):
        return {
            "status": "error",
            "issues": ["La CLABE no es válida (dígito verificador incorrecto)."],
        }
    if not bank_name or not bank_name.strip():
        return {"status": "error", "issues": ["Selecciona un banco."]}

    recipient_id = _recipient_id()
    created_at = _now()
    await database.execute(
        "INSERT INTO saved_recipients (id, user_id, alias, clabe, bank_name, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (recipient_id, user_id, alias.strip(), clabe, bank_name, created_at),
    )
    return {
        "status": "ok",
        "recipient": {
            "id": recipient_id,
            "alias": alias.strip(),
            "clabe": clabe,
            "bankName": bank_name,
            "createdAt": created_at,
        },
    }


async def transfer_funds(
    database: DatabasePort,
    user_id: str,
    source_account_id: str,
    amount: float,
    memo: str,
    destination: dict[str, Any],
) -> dict[str, Any]:
    """Move real, persisted money out of `source_account_id`.

    Deterministic and single-batch, same shape as `make_payment` (INV-015:
    the LLM never touches this math): validates funds and ownership first,
    then either (destination.kind == "own") debits the source and credits
    the destination account belonging to the same user in one write with two
    `transactions` rows, or (destination.kind == "external") debits the
    source only, records one `transactions` row, and optionally saves the
    recipient — all in a single `database.batch()`.
    """
    if amount is None or amount <= 0:
        return {"status": "error", "issues": ["El monto debe ser mayor a cero."]}

    kind = destination.get("kind") if destination else None
    if kind not in ("own", "external"):
        return {"status": "error", "issues": ["Destino de transferencia inválido."]}

    source_row = await database.fetch_one(
        "SELECT id, user_id, kind, institution, balance, currency FROM accounts "
        "WHERE id = ? AND user_id = ?",
        (source_account_id, user_id),
    )
    if source_row is None:
        return {"status": "error", "issues": ["No se encontró la cuenta de origen."]}
    if source_row["balance"] < amount:
        return {"status": "error", "issues": ["Fondos insuficientes en la cuenta de origen."]}

    occurred_on = date.today().isoformat()
    new_source_balance = round(source_row["balance"] - amount, 2)

    if kind == "own":
        destination_account_id = destination.get("account_id")
        if not destination_account_id or destination_account_id == source_account_id:
            return {
                "status": "error",
                "issues": ["La cuenta de origen y destino no pueden ser la misma."],
            }
        destination_row = await database.fetch_one(
            "SELECT id, user_id, kind, institution, balance, currency FROM accounts "
            "WHERE id = ? AND user_id = ?",
            (destination_account_id, user_id),
        )
        if destination_row is None:
            return {"status": "error", "issues": ["No se encontró la cuenta destino."]}

        new_destination_balance = round(destination_row["balance"] + amount, 2)
        transfer_id = _payment_id()
        credit_id = _payment_id()

        await database.batch(
            [
                (
                    "UPDATE accounts SET balance = ? WHERE id = ?",
                    (new_source_balance, source_row["id"]),
                ),
                (
                    "UPDATE accounts SET balance = ? WHERE id = ?",
                    (new_destination_balance, destination_row["id"]),
                ),
                (
                    "INSERT INTO transactions (id, user_id, account_id, occurred_on, amount, "
                    "direction, category, merchant, is_subscription, memo) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        transfer_id,
                        user_id,
                        source_row["id"],
                        occurred_on,
                        amount,
                        "out",
                        "transfer_own",
                        "Transferencia entre mis cuentas",
                        0,
                        memo,
                    ),
                ),
                (
                    "INSERT INTO transactions (id, user_id, account_id, occurred_on, amount, "
                    "direction, category, merchant, is_subscription, memo) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        credit_id,
                        user_id,
                        destination_row["id"],
                        occurred_on,
                        amount,
                        "in",
                        "transfer_own",
                        "Transferencia entre mis cuentas",
                        0,
                        memo,
                    ),
                ),
            ]
        )

        return {
            "status": "ok",
            "transfer": {
                "id": transfer_id,
                "amount": amount,
                "memo": memo,
                "occurredOn": occurred_on,
                "kind": "own",
            },
            "sourceAccount": {
                "id": source_row["id"],
                "userId": source_row["user_id"],
                "kind": source_row["kind"],
                "institution": source_row["institution"],
                "balance": new_source_balance,
                "currency": source_row["currency"],
            },
            "destinationAccount": {
                "id": destination_row["id"],
                "userId": destination_row["user_id"],
                "kind": destination_row["kind"],
                "institution": destination_row["institution"],
                "balance": new_destination_balance,
                "currency": destination_row["currency"],
            },
            "issues": [],
        }

    # kind == "external"
    clabe = destination.get("clabe", "")
    bank_name = destination.get("bank_name", "")
    alias = destination.get("alias", "")
    save_recipient = bool(destination.get("save_recipient", False))

    if not is_valid_clabe(clabe):
        return {
            "status": "error",
            "issues": ["La CLABE no es válida (dígito verificador incorrecto)."],
        }
    if not bank_name or not str(bank_name).strip():
        return {"status": "error", "issues": ["Selecciona un banco."]}

    transfer_id = _payment_id()
    statements = [
        (
            "UPDATE accounts SET balance = ? WHERE id = ?",
            (new_source_balance, source_row["id"]),
        ),
        (
            "INSERT INTO transactions (id, user_id, account_id, occurred_on, amount, "
            "direction, category, merchant, is_subscription, memo) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                transfer_id,
                user_id,
                source_row["id"],
                occurred_on,
                amount,
                "out",
                "transfer_external",
                alias or bank_name,
                0,
                memo,
            ),
        ),
    ]

    saved_recipient: dict[str, Any] | None = None
    if save_recipient:
        recipient_id = _recipient_id()
        created_at = _now()
        statements.append(
            (
                "INSERT INTO saved_recipients (id, user_id, alias, clabe, bank_name, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (recipient_id, user_id, (alias or bank_name).strip(), clabe, bank_name, created_at),
            )
        )
        saved_recipient = {
            "id": recipient_id,
            "alias": (alias or bank_name).strip(),
            "clabe": clabe,
            "bankName": bank_name,
            "createdAt": created_at,
        }

    await database.batch(statements)

    return {
        "status": "ok",
        "transfer": {
            "id": transfer_id,
            "amount": amount,
            "memo": memo,
            "occurredOn": occurred_on,
            "kind": "external",
        },
        "sourceAccount": {
            "id": source_row["id"],
            "userId": source_row["user_id"],
            "kind": source_row["kind"],
            "institution": source_row["institution"],
            "balance": new_source_balance,
            "currency": source_row["currency"],
        },
        "destinationAccount": None,
        "savedRecipient": saved_recipient,
        "issues": [],
    }


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


async def analyze_loans(
    database: DatabasePort, user_id: str, *, strategy: str = "avalanche"
) -> dict[str, Any]:
    """Deterministic loan analysis for the loans UI (INV-015)."""
    context = await financial_context(database, user_id)
    rows = await database.fetch_all(
        "SELECT occurred_on, amount, direction, category, merchant FROM transactions "
        "WHERE user_id = ? ORDER BY occurred_on DESC LIMIT 120",
        (user_id,),
    )
    transactions = [
        {
            "occurredOn": row["occurred_on"],
            "amount": row["amount"],
            "direction": row["direction"],
            "category": row["category"],
            "merchant": row["merchant"],
        }
        for row in rows
    ]
    return loans_analysis.analyze(context, strategy=strategy, transactions=transactions)


async def get_credit_history(
    database: DatabasePort, user_id: str, *, months: int = 6
) -> dict[str, Any]:
    """Compact credit picture for the loans consult prompt (not the A2UI model)."""
    profile = await get_profile(database, user_id)
    credits = await get_liabilities(database, user_id)
    cash_flow = await get_cash_flow(database, user_id, months)
    rows = await database.fetch_all(
        "SELECT substr(occurred_on, 1, 7) AS period, category, "
        "SUM(CASE WHEN direction = 'out' THEN amount ELSE 0 END) AS spent "
        "FROM transactions WHERE user_id = ? GROUP BY period, category "
        "ORDER BY period DESC, spent DESC",
        (user_id,),
    )
    spending: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        spending.setdefault(row["period"], []).append(
            {"category": row["category"], "spent": round(row["spent"], 2)}
        )
    txn_rows = await database.fetch_all(
        "SELECT id, occurred_on, amount, direction, category, merchant, is_subscription "
        "FROM transactions WHERE user_id = ? ORDER BY occurred_on DESC, id DESC LIMIT ?",
        (user_id, months * 5),
    )
    recent = [
        {
            "id": row["id"],
            "occurredOn": row["occurred_on"],
            "amount": row["amount"],
            "direction": row["direction"],
            "category": row["category"],
            "merchant": row["merchant"],
            "isSubscription": bool(row["is_subscription"]),
        }
        for row in txn_rows
    ]
    return {
        "profile": profile,
        "credits": credits,
        "totals": {
            "debt": round(sum(item["balance"] for item in credits), 2),
            "minPayment": round(sum(item["minPayment"] for item in credits), 2),
        },
        "monthlyCashFlow": cash_flow["months"],
        "spendingByCategory": spending,
        "recentTransactions": recent,
    }


async def _saving_goals(database: DatabasePort, user_id: str) -> list[dict[str, Any]]:
    rows = await database.fetch_all(
        "SELECT id, name, target_amount, target_date FROM saving_bags WHERE user_id = ?",
        (user_id,),
    )
    return [
        {
            "name": row["name"],
            "targetAmount": row["target_amount"],
            "targetDate": row["target_date"],
            "currentSaved": 0.0,
        }
        for row in rows
    ]


async def _payment_history(database: DatabasePort, user_id: str) -> list[dict[str, Any]]:
    rows = await database.fetch_all(
        "SELECT p.status FROM payment_history p "
        "JOIN liabilities l ON l.id = p.liability_id WHERE l.user_id = ?",
        (user_id,),
    )
    return [{"status": row["status"]} for row in rows]


async def compute_loan_offer(
    database: DatabasePort,
    user_id: str,
    *,
    requested_amount: float | None = None,
    apr: float = loan_offer.DEFAULT_APR,
    term_months: int = loan_offer.DEFAULT_TERM_MONTHS,
    opening_fee_pct: float = loan_offer.DEFAULT_OPENING_FEE_PCT,
    insurance_fee_pct: float = loan_offer.DEFAULT_INSURANCE_FEE_PCT,
    dti_cap: float = loan_offer.DEFAULT_DTI_CAP,
) -> dict[str, Any]:
    context = await financial_context(database, user_id)
    accounts = await get_accounts(database, user_id)
    policies = (await get_lender_policies(database))["policies"]
    goals = await _saving_goals(database, user_id)
    history = await _payment_history(database, user_id)
    return loan_offer.propose_offer(
        context,
        accounts=accounts,
        lender_policies=policies,
        saving_goals=goals,
        payment_history=history,
        requested_amount=requested_amount,
        apr=apr,
        term_months=term_months,
        opening_fee_pct=opening_fee_pct,
        insurance_fee_pct=insurance_fee_pct,
        dti_cap=dti_cap,
    )


async def store_loan_offer(
    database: DatabasePort,
    *,
    loan_request_id: str,
    user_id: str,
    offer: dict[str, Any],
) -> dict[str, Any]:
    terms = offer.get("offer") or offer
    offer_id = "ofr_" + uuid.uuid4().hex[:10]
    await database.execute(
        "INSERT INTO loan_offers (id, loan_request_id, user_id, amount, apr, term_months, "
        "opening_fee, insurance_fee, cat, monthly_payment, total_interest, total_cost, "
        "warnings_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            offer_id,
            loan_request_id,
            user_id,
            terms.get("amount"),
            terms.get("apr"),
            terms.get("termMonths"),
            terms.get("openingFee", 0.0),
            terms.get("insuranceFee", 0.0),
            terms.get("cat", 0.0),
            terms.get("monthlyPayment"),
            terms.get("totalInterest", 0.0),
            terms.get("totalCost", 0.0),
            json.dumps(offer.get("warnings", []), ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return {"status": "ok", "offer_id": offer_id}


async def create_loan(
    database: DatabasePort,
    user_id: str,
    *,
    amount: float,
    apr: float = loan_offer.DEFAULT_APR,
    term_months: int = loan_offer.DEFAULT_TERM_MONTHS,
    loan_request_id: str | None = None,
) -> dict[str, Any]:
    if amount is None or float(amount) <= 0:
        return {"status": "error", "issues": ["amount must be positive"]}

    if loan_request_id:
        offered = await database.fetch_one(
            "SELECT amount, apr, term_months, opening_fee, insurance_fee FROM loan_offers "
            "WHERE loan_request_id = ? ORDER BY created_at DESC LIMIT 1",
            (loan_request_id,),
        )
        if offered is not None:
            if float(amount) > float(offered["amount"]) + 0.01:
                return {
                    "status": "error",
                    "issues": ["amount exceeds the offered amount"],
                }
            apr = float(offered["apr"])
            term_months = int(offered["term_months"])

    terms = loan_offer.terms_for(amount, apr=apr, term_months=term_months)
    loan_id = "loan_" + uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc).isoformat()

    account = await database.fetch_one(
        "SELECT id, balance FROM accounts WHERE user_id = ? AND kind = 'checking' "
        "ORDER BY id LIMIT 1",
        (user_id,),
    )
    statements: list[tuple[str, tuple]] = [
        (
            "INSERT INTO loans (id, user_id, loan_request_id, amount, apr, term_months, "
            "opening_fee, insurance_fee, cat, monthly_payment, total_interest, total_cost, "
            "status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                loan_id,
                user_id,
                loan_request_id,
                terms["amount"],
                terms["apr"],
                terms["termMonths"],
                terms["openingFee"],
                terms["insuranceFee"],
                terms["cat"],
                terms["monthlyPayment"],
                terms["totalInterest"],
                terms["totalCost"],
                "active",
                now,
            ),
        )
    ]
    if account is not None:
        statements.append(
            (
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (round(float(account["balance"]) + terms["amount"], 2), account["id"]),
            )
        )
        statements.append(
            (
                "INSERT INTO transactions (id, user_id, account_id, occurred_on, amount, "
                "direction, category, merchant, is_subscription) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "t_loan_" + uuid.uuid4().hex[:8],
                    user_id,
                    account["id"],
                    now[:10],
                    terms["amount"],
                    "in",
                    "loan_disbursement",
                    "Crédito La Mesa",
                    0,
                ),
            )
        )
    await database.batch(statements)
    return {"status": "ok", "loan": {"id": loan_id, "userId": user_id, **terms}}
