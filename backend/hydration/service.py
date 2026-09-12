"""Hydration service: resolve placeholders and structurally revalidate.

Revalidation is deterministic (INV-015): when a surface carries a `simulation`
descriptor, the engine recomputes the plan from fresh data and a canonical
`plan-section` is inserted/updated (and a `BreakAlert` added or removed) so the
interface structure changes when financial reality changes (INV-022).
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from engine import planning

from . import assumptions as assumptions_builder
from .placeholders import resolve_placeholders

PLAN_SECTION_ID = "plan-section"
PLAN_TABLE_ID = "plan-table"
BREAK_ALERT_ID = "break-alert"

_PLAN_SECTION_BINDINGS: dict[str, Any] = {
    "months": {"path": "/plan/months"},
    "breakMonth": {"path": "/plan/breakMonth"},
}
_BREAK_ALERT_BINDINGS: dict[str, Any] = {
    "month": {"path": "/plan/break/month"},
    "shortfall": {"path": "/plan/break/shortfall"},
}


def _index_of(components: list[dict[str, Any]], component_id: str) -> int | None:
    for index, component in enumerate(components):
        if component.get("id") == component_id:
            return index
    return None


def _upsert(components: list[dict[str, Any]], component: dict[str, Any]) -> None:
    index = _index_of(components, component["id"])
    if index is None:
        components.append(component)
    else:
        components[index] = component


def _remove(components: list[dict[str, Any]], component_id: str) -> None:
    index = _index_of(components, component_id)
    if index is not None:
        components.pop(index)


def _root_column(components: list[dict[str, Any]]) -> dict[str, Any] | None:
    root_index = _index_of(components, "root")
    if root_index is not None:
        root = components[root_index]
        if root.get("component") == "Column":
            return root
    for component in components:
        if component.get("component") == "Column":
            return component
    return None


def _apply_plan_section(components: list[dict[str, Any]], plan: Mapping[str, Any]) -> None:
    section_children = [PLAN_TABLE_ID]
    _upsert(
        components,
        {"id": PLAN_TABLE_ID, "component": "PlanTable", **_PLAN_SECTION_BINDINGS},
    )
    if plan.get("break") is not None:
        _upsert(
            components,
            {"id": BREAK_ALERT_ID, "component": "BreakAlert", **_BREAK_ALERT_BINDINGS},
        )
        section_children.append(BREAK_ALERT_ID)
    else:
        _remove(components, BREAK_ALERT_ID)

    _upsert(
        components,
        {
            "id": PLAN_SECTION_ID,
            "component": "Column",
            "children": section_children,
            "gap": 12,
        },
    )

    root = _root_column(components)
    if root is not None:
        children = root.get("children")
        if not isinstance(children, list):
            children = []
        if PLAN_SECTION_ID not in children:
            children.append(PLAN_SECTION_ID)
        root["children"] = children


def _apply_assumptions_section(
    components: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    simulation: Mapping[str, Any] | None = None,
) -> None:
    for index in range(len(components) - 1, -1, -1):
        component_id = components[index].get("id")
        if component_id == assumptions_builder.SECTION_ID or (
            isinstance(component_id, str) and component_id.startswith("assumption-")
        ):
            components.pop(index)

    injected = assumptions_builder.build_assumption_components(context, simulation=simulation)
    if not injected:
        return
    components.extend(injected)

    root = _root_column(components)
    if root is not None:
        children = root.get("children")
        if not isinstance(children, list):
            children = []
        if assumptions_builder.SECTION_ID not in children:
            children.append(assumptions_builder.SECTION_ID)
        root["children"] = children


def revalidate(
    template: Any,
    context: dict[str, Any],
    *,
    simulation: Mapping[str, Any] | None = None,
) -> Any:
    if simulation:
        plan = planning.build_plan(context, simulation)
        context["plan"] = plan
    if not isinstance(template, list):
        return template
    components = copy.deepcopy(template)
    if context.get("plan") is not None:
        _apply_plan_section(components, context["plan"])
    return components


def revalidate_assumptions(
    template: Any,
    context: dict[str, Any],
    *,
    simulation: Mapping[str, Any] | None = None,
) -> Any:
    if not isinstance(template, list):
        return template
    components = copy.deepcopy(template)
    _apply_assumptions_section(components, context, simulation=simulation)
    return components


def hydrate_components(
    template: Any,
    context: dict[str, Any],
    *,
    simulation: Mapping[str, Any] | None = None,
) -> Any:
    resolved = resolve_placeholders(template, context)
    resolved = revalidate(resolved, context, simulation=simulation)
    resolved = revalidate_assumptions(resolved, context, simulation=simulation)
    return resolved
