"""System-prompt generation from the machine-readable catalog."""

from __future__ import annotations

from .catalog import CATALOG, Catalog


def describe_components(catalog: Catalog = CATALOG) -> str:
    lines = []
    for name, spec in catalog.components.items():
        required = ", ".join(spec.required) if spec.required else "none"
        props = ", ".join(f"{prop}: {token}" for prop, token in spec.props.items()) or "none"
        lines.append(f"- {name} | required: {required} | props: {props}")
    return "\n".join(lines)


def build_system_prompt(
    *,
    role_description: str,
    ui_description: str = "",
    terminal_tool: str = "persist_ui",
    catalog: Catalog = CATALOG,
) -> str:
    return "\n".join(
        [
            role_description.strip(),
            "",
            f"You generate interfaces using the A2UI protocol (version {catalog.version}) for the "
            f"catalog {catalog.catalog_id!r}.",
            "",
            "MESSAGE TYPES: " + ", ".join(catalog.messages),
            "DATA BINDING: a prop value may be a literal or a JSON-Pointer binding of the form "
            '{"path": "/liabilities/0/balance"}. Bindings resolve against the surface data model, '
            "whose root keys are: profile, liabilities, totals, incomeStreams, subscriptions, "
            "subscriptionTotal, cashFlow, plan, speech. Prefer bindings over hard-coded "
            "financial values.",
            "COMPONENT SHAPE (v0.9, flat): each component is an object with a STRING type and "
            'sibling props, e.g. {"id": "title", "component": "Heading", "text": "Hola", '
            '"level": 1}. Never nest props under the type name.',
            "",
            "ALLOWED COMPONENTS (use ONLY these):",
            describe_components(catalog),
            "",
            "ALLOWED ACTIONS: " + ", ".join(catalog.actions),
            "",
            "OUTPUT CONTRACT:",
            f"- Do not render UI in text. Your final step MUST be a call to the {terminal_tool} tool.",
            f"- Call {terminal_tool} with: domain, entity_id, catalog_id={catalog.catalog_id!r}, "
            "components (an A2UI adjacency list), and data_model (an object).",
            "- Exactly ONE component must have \"id\": \"root\" — this is the entry point the client "
            "renders first. Every other component MUST be reachable from \"root\" via children/child. "
            "A surface with no component whose id is \"root\" is never displayed to the user.",
            "- Components must follow the exact prop names above. Unknown components or props are "
            "rejected and the call will fail.",
            "",
            ui_description.strip(),
        ]
    ).strip()


def catalog_summary(catalog: Catalog = CATALOG) -> dict[str, object]:
    return {
        "catalog_id": catalog.catalog_id,
        "version": catalog.version,
        "messages": list(catalog.messages),
        "actions": list(catalog.actions),
        "components": list(catalog.component_names()),
    }
