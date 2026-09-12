"""Saving-bag domain service: persistence plus deterministic estimates.

Research snapshots are immutable (REQ-BAG-04): every run inserts a new row and
the estimate/feasibility always read the latest snapshot. All numbers come from
`engine.savings` (INV-015); live research runs only on create/refresh.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from db.port import DatabasePort
from engine import savings as savings_engine
from providers.research import ResearchProvider

from ..finance import service as finance_service


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bag_id() -> str:
    return "bag_" + uuid.uuid4().hex[:10]


def _row_to_bag(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "name": row["name"],
        "targetAmount": row["target_amount"],
        "targetDate": row["target_date"],
        "status": row["status"],
        "currency": row["currency"],
        "createdAt": row["created_at"],
    }


async def create_bag(
    database: DatabasePort,
    *,
    user_id: str,
    name: str,
    target_amount: float | None = None,
    target_date: str | None = None,
) -> dict[str, Any]:
    bag_id = _bag_id()
    await database.execute(
        "INSERT INTO saving_bags (id, user_id, name, target_amount, target_date, status, "
        "currency, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (bag_id, user_id, name, target_amount, target_date, "draft", "MXN", _now()),
    )
    bag = await get_bag(database, bag_id)
    return {"status": "ok", "bag": bag}


async def get_bag(database: DatabasePort, bag_id: str) -> dict[str, Any] | None:
    row = await database.fetch_one(
        "SELECT id, user_id, name, target_amount, target_date, status, currency, created_at "
        "FROM saving_bags WHERE id = ?",
        (bag_id,),
    )
    return _row_to_bag(row) if row else None


async def list_bags(database: DatabasePort, user_id: str) -> list[dict[str, Any]]:
    rows = await database.fetch_all(
        "SELECT id, user_id, name, target_amount, target_date, status, currency, created_at "
        "FROM saving_bags WHERE user_id = ? ORDER BY created_at DESC, id ASC",
        (user_id,),
    )
    return [_row_to_bag(row) for row in rows]


async def _set_status(database: DatabasePort, bag_id: str, status: str) -> None:
    await database.execute("UPDATE saving_bags SET status = ? WHERE id = ?", (status, bag_id))


async def get_answers(database: DatabasePort, bag_id: str) -> dict[str, str]:
    rows = await database.fetch_all(
        "SELECT question_key, answer FROM saving_bag_answers WHERE bag_id = ? ORDER BY id",
        (bag_id,),
    )
    return {row["question_key"]: row["answer"] for row in rows}


async def answer_bag(
    database: DatabasePort, bag_id: str, answers: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    bag = await get_bag(database, bag_id)
    if bag is None:
        return {"status": "error", "issues": [f"unknown bag {bag_id!r}"]}

    normalized: list[tuple[str, str]] = []
    for index, item in enumerate(answers):
        if not isinstance(item, Mapping):
            continue
        key = str(item.get("question_key") or item.get("key") or f"q{index}")
        value = item.get("answer", item.get("value"))
        normalized.append((key, "" if value is None else str(value)))

    for key, _ in normalized:
        await database.execute(
            "DELETE FROM saving_bag_answers WHERE bag_id = ? AND question_key = ?", (bag_id, key)
        )
    now = _now()
    for key, value in normalized:
        await database.execute(
            "INSERT INTO saving_bag_answers (id, bag_id, question_key, answer, answered_at) "
            "VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, bag_id, key, value, now),
        )
    await _set_status(database, bag_id, "planning")
    return {"status": "ok", "bag": bag, "answers": await get_answers(database, bag_id)}


async def get_research(database: DatabasePort, bag_id: str) -> dict[str, Any] | None:
    row = await database.fetch_one(
        "SELECT id, source, payload_json, fetched_at FROM saving_bag_research "
        "WHERE bag_id = ? ORDER BY fetched_at DESC, rowid DESC LIMIT 1",
        (bag_id,),
    )
    if row is None:
        return None
    return {
        "id": row["id"],
        "source": row["source"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "fetchedAt": row["fetched_at"],
    }


async def research_costs(
    database: DatabasePort,
    bag_id: str,
    research: ResearchProvider,
    *,
    query: str | None = None,
    hints: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    bag = await get_bag(database, bag_id)
    if bag is None:
        return {"status": "error", "issues": [f"unknown bag {bag_id!r}"]}
    answers = await get_answers(database, bag_id)
    snapshot = await research.research(query or bag["name"], dict(hints or answers))
    await database.execute(
        "INSERT INTO saving_bag_research (id, bag_id, source, payload_json, fetched_at) "
        "VALUES (?,?,?,?,?)",
        (
            uuid.uuid4().hex,
            bag_id,
            snapshot.source,
            json.dumps(snapshot.payload, ensure_ascii=False),
            _now(),
        ),
    )
    await _set_status(database, bag_id, "researching")
    return {
        "status": "ok",
        "bag": bag,
        "research": await get_research(database, bag_id),
    }


async def estimate_total(database: DatabasePort, bag_id: str) -> dict[str, Any]:
    bag = await get_bag(database, bag_id)
    if bag is None:
        return {"status": "error", "issues": [f"unknown bag {bag_id!r}"]}
    snapshot = await get_research(database, bag_id)
    answers = await get_answers(database, bag_id)
    payload = snapshot["payload"] if snapshot else {}
    estimate = savings_engine.estimate_total(payload, answers)
    estimate["goal"] = savings_engine.goal_gap(bag["targetAmount"], estimate["estimatedTotal"])
    estimate["status"] = "ok"
    estimate["source"] = snapshot["source"] if snapshot else "none"
    return estimate


async def _savings_balance(database: DatabasePort, user_id: str) -> float:
    row = await database.fetch_one(
        "SELECT COALESCE(SUM(balance), 0) AS total FROM accounts "
        "WHERE user_id = ? AND kind = 'savings'",
        (user_id,),
    )
    return round(float(row["total"]) if row else 0.0, 2)


async def build_plan(
    database: DatabasePort,
    bag_id: str,
    *,
    today: date | None = None,
    goal_reduced: bool = False,
) -> dict[str, Any]:
    bag = await get_bag(database, bag_id)
    if bag is None:
        return {"status": "error", "issues": [f"unknown bag {bag_id!r}"]}
    snapshot = await get_research(database, bag_id)
    answers = await get_answers(database, bag_id)
    context = await finance_service.financial_context(database, bag["userId"])
    current_saved = await _savings_balance(database, bag["userId"])
    plan = savings_engine.build_savings_plan(
        context,
        {"target_amount": bag["targetAmount"], "target_date": bag["targetDate"]},
        snapshot["payload"] if snapshot else {},
        answers,
        current_saved=current_saved,
        today=today,
        goal_reduced=goal_reduced,
    )
    plan["bagId"] = bag_id
    plan["bagName"] = bag["name"]
    return {"status": "ok", "bag": bag, "plan": plan, "researchSource": snapshot["source"] if snapshot else "none"}


async def compute_feasibility(
    database: DatabasePort, bag_id: str, *, today: date | None = None, goal_reduced: bool = False
) -> dict[str, Any]:
    result = await build_plan(database, bag_id, today=today, goal_reduced=goal_reduced)
    if result.get("status") != "ok":
        return result
    plan = result["plan"]
    existing = await database.fetch_one(
        "SELECT id FROM saving_bag_plan WHERE bag_id = ? ORDER BY updated_at DESC, rowid DESC LIMIT 1",
        (bag_id,),
    )
    if existing is None:
        await database.execute(
            "INSERT INTO saving_bag_plan (id, bag_id, plan_json, feasibility, projected_date, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                uuid.uuid4().hex,
                bag_id,
                json.dumps(plan, ensure_ascii=False),
                plan["feasibility"],
                plan["projectedDate"],
                _now(),
            ),
        )
    else:
        await database.execute(
            "UPDATE saving_bag_plan SET plan_json = ?, feasibility = ?, projected_date = ?, "
            "updated_at = ? WHERE id = ?",
            (json.dumps(plan, ensure_ascii=False), plan["feasibility"], plan["projectedDate"], _now(), existing["id"]),
        )
    await _set_status(database, bag_id, "planned")
    return {"status": "ok", "bag": result["bag"], "plan": plan}


async def get_plan(database: DatabasePort, bag_id: str) -> dict[str, Any] | None:
    row = await database.fetch_one(
        "SELECT plan_json, feasibility, projected_date, updated_at FROM saving_bag_plan "
        "WHERE bag_id = ? ORDER BY updated_at DESC, rowid DESC LIMIT 1",
        (bag_id,),
    )
    if row is None:
        return None
    plan = json.loads(row["plan_json"] or "{}")
    plan.setdefault("feasibility", row["feasibility"])
    plan.setdefault("projectedDate", row["projected_date"])
    return plan


async def refresh_bag(
    database: DatabasePort, bag_id: str, research: ResearchProvider
) -> dict[str, Any]:
    refreshed = await research_costs(database, bag_id, research)
    if refreshed.get("status") != "ok":
        return refreshed
    computed = await compute_feasibility(database, bag_id)
    return {
        "status": "ok",
        "bag": computed["bag"],
        "research": refreshed["research"],
        "plan": computed["plan"],
    }


async def savings_snapshot(
    database: DatabasePort, bag_id: str, *, today: date | None = None
) -> dict[str, Any] | None:
    """Complete view used as the `/savings` A2UI data model and for revalidation."""
    bag = await get_bag(database, bag_id)
    if bag is None:
        return None
    return {
        "bag": bag,
        "answers": await get_answers(database, bag_id),
        "research": await get_research(database, bag_id),
        "estimate": await estimate_total(database, bag_id),
        "plan": await get_plan(database, bag_id),
    }
