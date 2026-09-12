"""Deterministic mock seed (REQ-DATA-02).

No randomness leaks between runs: the generator uses a fixed seed and fixed
timestamps, so the database is reproducible.
"""

from __future__ import annotations

import random
from datetime import date
from typing import Any, Iterable, Sequence

from .port import DatabasePort

NOW = "2026-09-12T12:00:00Z"

Columns = Sequence[str]
Rows = Iterable[Sequence[Any]]


def _inserts(table: str, columns: Columns, rows: Rows) -> list[tuple[str, tuple]]:
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    return [(sql, tuple(row)) for row in rows]


def _transaction_rows() -> list[tuple]:
    rng = random.Random(7)
    rows: list[tuple] = []
    counter = 0

    def add(day: int, amount: float, direction: str, category: str, merchant: str, sub: int = 0) -> None:
        nonlocal counter
        counter += 1
        try:
            occurred = date(2026, month, day)
        except ValueError:
            occurred = date(2026, month, 28)
        rows.append(
            (
                f"t_{counter:04d}",
                "u_ana",
                "a_ana_nom",
                occurred.isoformat(),
                round(amount, 2),
                direction,
                category,
                merchant,
                sub,
            )
        )

    for month in range(3, 9):
        add(15, 9500.0, "in", "nomina", "Nómina BBVA")
        add(28, 9500.0, "in", "nomina", "Nómina BBVA")
        add(1, 6000.0, "out", "renta", "Renta")
        for _ in range(4):
            add(rng.randint(2, 27), rng.uniform(900, 1900), "out", "despensa", rng.choice(["Soriana", "Walmart", "Chedraui", "La Comer"]))
        for _ in range(3):
            add(rng.randint(2, 27), rng.uniform(300, 700), "out", "transporte", rng.choice(["Uber", "Metro", "Gasolina"]))
        for _ in range(3):
            add(rng.randint(2, 27), rng.uniform(200, 600), "out", "restaurantes", rng.choice(["Tacos", "Café", "Sushi"]))
        add(5, 219.0, "out", "suscripcion", "Netflix", 1)
        add(8, 129.0, "out", "suscripcion", "Spotify", 1)
        add(10, 599.0, "out", "suscripcion", "Smart Fit", 1)

    return rows


def build_seed_statements() -> list[tuple[str, tuple]]:
    statements: list[tuple[str, tuple]] = []

    statements += _inserts(
        "users",
        ("id", "name", "age", "city", "monthly_income", "pay_frequency", "credit_score", "created_at"),
        [
            ("u_ana", "Ana López", 32, "CDMX", 19000.0, "quincenal", 640, NOW),
            ("u_don", "Don Miguel", 71, "Puebla", 7200.0, "mensual", 590, NOW),
        ],
    )

    statements += _inserts(
        "accounts",
        ("id", "user_id", "kind", "institution", "balance", "currency"),
        [
            ("a_ana_nom", "u_ana", "checking", "BBVA", 8500.0, "MXN"),
            ("a_ana_ahorro", "u_ana", "savings", "BBVA", 3000.0, "MXN"),
            ("a_don_nom", "u_don", "checking", "Banorte", 2100.0, "MXN"),
        ],
    )

    statements += _inserts(
        "income_streams",
        ("id", "user_id", "source", "amount", "frequency", "next_date"),
        [
            ("i_ana", "u_ana", "Nómina", 9500.0, "quincenal", "2026-09-15"),
            ("i_don", "u_don", "Pensión", 7200.0, "mensual", "2026-10-01"),
        ],
    )

    statements += _inserts(
        "subscriptions",
        ("id", "user_id", "merchant", "amount", "period", "next_charge"),
        [
            ("s_netflix", "u_ana", "Netflix", 219.0, "mensual", "2026-10-05"),
            ("s_spotify", "u_ana", "Spotify", 129.0, "mensual", "2026-10-08"),
            ("s_gym", "u_ana", "Smart Fit", 599.0, "mensual", "2026-10-10"),
            ("s_tel", "u_don", "Telcel", 200.0, "mensual", "2026-10-02"),
        ],
    )

    statements += _inserts(
        "liabilities",
        ("id", "user_id", "creditor", "kind", "principal", "balance", "apr", "min_payment", "due_day", "nomina_discount", "status"),
        [
            ("l_bbva_tdc", "u_ana", "BBVA", "credit_card", 60000.0, 48000.0, 0.54, 2900.0, 5, 0.0, "active"),
            ("l_banorte_tdc", "u_ana", "Banorte", "credit_card", 26000.0, 22000.0, 0.48, 1350.0, 12, 0.0, "active"),
            ("l_nomina", "u_ana", "BBVA", "payroll_loan", 40000.0, 35000.0, 0.28, 1800.0, 15, 1800.0, "active"),
            ("l_personal", "u_ana", "Kueski", "personal_loan", 18000.0, 15000.0, 0.35, 1100.0, 20, 0.0, "active"),
            ("l_electronica", "u_ana", "Elektra", "store_credit", 9000.0, 7200.0, 0.62, 700.0, 8, 0.0, "active"),
        ],
    )

    statements += _inserts(
        "lender_policies",
        ("id", "creditor", "strategy", "min_settlement_pct", "max_months", "apr_floor", "accepts_consolidation"),
        [
            ("p_bbva_consolidate", "BBVA", "consolidation", 1.00, 48, 0.24, 1),
            ("p_bbva_settle", "BBVA", "settlement", 0.70, 12, 0.00, 0),
            ("p_banorte_settle", "Banorte", "settlement", 0.75, 12, 0.00, 0),
            ("p_nomina_restructure", "BBVA", "restructure", 1.00, 36, 0.22, 0),
        ],
    )

    statements += _inserts(
        "saving_bags",
        ("id", "user_id", "name", "target_amount", "target_date", "status", "currency", "created_at"),
        [("bag_japon", "u_ana", "Viaje a Japón", 45000.0, "2027-04-01", "researching", "MXN", NOW)],
    )

    statements += _inserts(
        "saving_bag_answers",
        ("id", "bag_id", "question_key", "answer", "answered_at"),
        [
            ("ba_japon_1", "bag_japon", "when", "abril 2027", NOW),
            ("ba_japon_2", "bag_japon", "days", "10", NOW),
            ("ba_japon_3", "bag_japon", "origin", "CDMX", NOW),
            ("ba_japon_4", "bag_japon", "travelers", "2", NOW),
            ("ba_japon_5", "bag_japon", "style", "mochilero", NOW),
        ],
    )

    statements += _inserts(
        "saving_bag_research",
        ("id", "bag_id", "source", "payload_json", "fetched_at"),
        [
            (
                "br_japon",
                "bag_japon",
                "gemini_grounding",
                '{"flight_roundtrip_mxn": 28000, "lodging_per_night_mxn": 1400, "food_per_day_mxn": 700, "transport_per_day_mxn": 250}',
                NOW,
            )
        ],
    )

    statements += _inserts(
        "saving_bag_plan",
        ("id", "bag_id", "plan_json", "feasibility", "projected_date", "updated_at"),
        [
            (
                "bp_japon",
                "bag_japon",
                '{"monthly_capacity": 3200, "months_needed": 16, "gap_mxn": 8500}',
                "tight",
                "2027-05-20",
                NOW,
            )
        ],
    )

    statements += _inserts(
        "accessibility_profiles",
        ("id", "user_id", "mode", "voice_id", "language", "speed", "enabled_reason"),
        [("ap_don", "u_don", "low_literacy", "", "es-MX", 0.95, "flagged: elderly + low_literacy")],
    )

    statements += _inserts(
        "generated_ui",
        ("id", "user_id", "domain", "entity_id", "catalog_id", "template_json", "bindings_json", "version", "audience", "created_at", "updated_at"),
        [
            (
                "g_ana_plan",
                "u_ana",
                "loans_credits",
                None,
                "standard",
                '{"id":"root","component":{"Column":{"children":["balance","break-alert"]}}}',
                '{"balance":"{{finance.total_debt}}"}',
                1,
                "user",
                NOW,
                NOW,
            )
        ],
    )

    statements += _inserts(
        "sessions",
        ("id", "user_id", "active_surface_id", "context_json", "created_at", "updated_at"),
        [("s_ana", "u_ana", "g_ana_plan", "{}", NOW, NOW)],
    )

    statements += _inserts(
        "transactions",
        ("id", "user_id", "account_id", "occurred_on", "amount", "direction", "category", "merchant", "is_subscription"),
        _transaction_rows(),
    )

    return statements


async def seed(database: DatabasePort) -> None:
    """Idempotent: clears showcase tables, then applies the deterministic seed."""
    tables = [
        "transactions",
        "sessions",
        "generated_ui",
        "accessibility_profiles",
        "saving_bag_plan",
        "saving_bag_research",
        "saving_bag_answers",
        "saving_bags",
        "lender_policies",
        "liabilities",
        "subscriptions",
        "income_streams",
        "accounts",
        "users",
    ]
    await database.batch([(f"DELETE FROM {table}", ()) for table in tables])
    await database.batch(build_seed_statements())
