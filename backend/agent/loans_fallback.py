"""Deterministic, engine-backed loans terminal (latency safety net).

When the LLM overruns the consult deadline, the provider is unavailable, or its
output cannot be normalized into a valid A2UI payload, we still owe the user a
correct, schema-valid interface within the latency budget. This module builds one
from the deterministic engine results (`compute_loan_offer` + `analyze_loans`),
using only components the mobile catalog implements. Pure and deterministic
(INV-015); it never invents financial figures.
"""

from __future__ import annotations

from typing import Any, Mapping

from ui_contract.catalog import CATALOG_ID


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _first_name(profile: Mapping[str, Any] | None) -> str:
    name = str((profile or {}).get("name") or "").strip()
    return name.split()[0] if name else ""


def _propose(offer: Any) -> dict[str, Any]:
    """Unwrap the `compute_loan_offer` tool result into the propose_offer dict."""
    if not isinstance(offer, Mapping):
        return {}
    inner = offer.get("offer")
    if isinstance(inner, Mapping):
        return dict(inner)
    return dict(offer)


def _loan_offer_component() -> dict[str, Any]:
    return {
        "id": "offer",
        "component": "LoanOffer",
        "amount": {"path": "/loan/amount"},
        "apr": {"path": "/loan/apr"},
        "months": {"path": "/loan/termMonths"},
        "monthlyPayment": {"path": "/loan/monthlyPayment"},
        "totalInterest": {"path": "/loan/totalInterest"},
        "totalCost": {"path": "/loan/totalCost"},
        "cat": {"path": "/loan/cat"},
        "schedule": {"path": "/loan/schedule"},
        "action": {"event": {"name": "request_loan", "context": {}}},
    }


def build_terminal(
    *,
    profile: Mapping[str, Any] | None = None,
    audience: Mapping[str, Any] | None = None,
    offer: Any = None,
    analysis: Any = None,
) -> dict[str, Any]:
    """Return `{response_text, terminal_response}`; terminal is None when not eligible."""
    propose = _propose(offer)
    terms = propose.get("offer") if isinstance(propose.get("offer"), Mapping) else {}
    warning_list = list(propose.get("warnings") or [])
    affordable = bool(propose.get("affordable")) and float(terms.get("amount") or 0.0) > 0
    name = _first_name(profile)
    analysis_payload = (analysis or {}).get("analysis") if isinstance(analysis, Mapping) else None
    analysis_payload = analysis_payload if isinstance(analysis_payload, Mapping) else {}

    if not affordable:
        best = analysis_payload.get("nextBestAction") or {}
        hint = str(best.get("summary") or best.get("action") or "").strip()
        text = (
            f"{name + ', c' if name else 'C'}on tu ingreso y tus gastos actuales no hay margen "
            "para un crédito nuevo en este momento."
        )
        if warning_list:
            text += " " + str(warning_list[0])
        if hint:
            text += f" Mientras tanto: {hint}."
        return {"response_text": text, "terminal_response": None}

    amount = terms.get("amount")
    payment = terms.get("monthlyPayment")
    months = terms.get("termMonths")
    cat = terms.get("cat")
    text = (
        f"{name + ', t' if name else 'T'}e puedo ofrecer {_money(amount)} a {int(months or 0)} meses "
        f"con un pago mensual de {_money(payment)}. El CAT aproximado es {float(cat or 0.0):.1f}%."
    )
    if warning_list:
        text += " " + str(warning_list[0])

    components: list[dict[str, Any]] = [
        {"id": "root", "component": "Column", "gap": 12, "children": ["h1", "intro"]},
        {
            "id": "h1",
            "component": "Heading",
            "level": 1,
            "text": f"Tu oferta de crédito{', ' + name if name else ''}",
        },
        {"id": "intro", "component": "Text", "variant": "body", "text": text},
    ]

    scenarios = analysis_payload.get("scenarios") or []
    if scenarios:
        components.append(
            {
                "id": "scenarios",
                "component": "ScenarioComparison",
                "title": "Escenarios de pago",
                "highlightIndex": 2,
                "scenarios": scenarios,
            }
        )
        components[0]["children"].append("scenarios")

    components.append(_loan_offer_component())
    components[0]["children"].append("offer")

    if warning_list:
        warn_children = [f"warn_{index}" for index in range(len(warning_list))]
        components.append(
            {
                "id": "warn_title",
                "component": "Heading",
                "level": 2,
                "text": "Factores a considerar",
            }
        )
        components[0]["children"].append("warn_title")
        for index, warning in enumerate(warning_list):
            components.append(
                {"id": f"warn_{index}", "component": "Text", "variant": "caption", "text": str(warning)}
            )
            components[0]["children"].append(f"warn_{index}")

    data_model = {
        "audience": dict(audience or {}),
        "profile": {"name": (profile or {}).get("name")},
        "loan": {
            **terms,
            "schedule": propose.get("schedule") or [],
            "risk": propose.get("risk") or {},
            "warnings": warning_list,
        },
    }
    terminal = {"catalog_id": CATALOG_ID, "components": components, "data_model": data_model}
    return {"response_text": text, "terminal_response": terminal}
