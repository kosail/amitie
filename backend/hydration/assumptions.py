"""Caja de Cristal: the "why you are seeing this" assumptions panel.

Assumptions are derived from the same deterministic inputs the engine used, so
the panel exposes real data and at least one assumption is editable. The chip's
action returns to the agent through the normal A2UI closed loop (INV-017).
"""

from __future__ import annotations

from typing import Any, Mapping

from engine import planning

SECTION_ID = "assumptions-section"
CARD_TITLE = "¿Por qué ves esto?"


def _debt_assumptions(
    context: Mapping[str, Any], simulation: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    inputs = planning.simulation_inputs(context)
    sim = simulation or {}
    return [
        {"key": "monthlyIncome", "label": "Ingreso mensual", "value": inputs["monthlyIncome"], "editable": False},
        {"key": "monthlyExpenses", "label": "Gastos mensuales", "value": inputs["monthlyExpenses"], "editable": False},
        {"key": "minPayment", "label": "Pagos mínimos", "value": inputs["minPayment"], "editable": False},
        {
            "key": "strategy",
            "label": "Estrategia",
            "value": str(sim.get("strategy") or planning.DEFAULT_STRATEGY),
            "editable": False,
        },
        {"key": "extra_income", "label": "Ingreso extra mensual", "value": float(sim.get("extra_income") or 0.0), "editable": True},
        {"key": "extra_payment", "label": "Pago extra mensual", "value": float(sim.get("extra_payment") or 0.0), "editable": True},
        {"key": "expense_reduction", "label": "Recorte de gastos", "value": float(sim.get("expense_reduction") or 0.0), "editable": True},
        {"key": "horizon_months", "label": "Horizonte (meses)", "value": int(sim.get("horizon_months") or 36), "editable": False},
    ]


def _savings_assumptions_unused() -> None:  # pragma: no cover - staged, not wired
    """Saving Bags is PENDING TO BE RELEASED; retained only as reference."""
    return None


def build_assumptions(
    context: Mapping[str, Any],
    *,
    simulation: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(context, Mapping) and context.get("plan") is not None:
        return _debt_assumptions(context, simulation)
    return []


def build_assumption_components(
    context: Mapping[str, Any],
    *,
    simulation: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    assumptions = build_assumptions(context, simulation=simulation)
    if not assumptions:
        return []

    chips: list[dict[str, Any]] = []
    chip_ids: list[str] = []
    for item in assumptions:
        path = f"/assumptions/{item['key']}"
        chip: dict[str, Any] = {
            "id": f"assumption-{item['key']}",
            "component": "AssumptionChip",
            "label": item["label"],
            "value": item["value"],
            "path": path,
        }
        if item.get("editable"):
            chip["editable"] = True
            chip["action"] = {
                "event": {"name": "toggle_assumption", "context": {"key": item["key"], "path": path}}
            }
        chips.append(chip)
        chip_ids.append(chip["id"])

    section = {
        "id": SECTION_ID,
        "component": "Card",
        "title": CARD_TITLE,
        "tone": "neutral",
        "children": chip_ids,
    }
    return [section, *chips]
