"""UI MCP server: persist, hydrate, and log A2UI actions."""

from __future__ import annotations

from typing import Any

from db.port import DatabasePort
from mcp.server import MCPServer

from . import service


def build_ui_server(database: DatabasePort) -> MCPServer:
    server = MCPServer("ui")

    @server.tool()
    async def persist_ui(
        user_id: str,
        domain: str,
        catalog_id: str,
        components: list[dict[str, Any]],
        data_model: dict[str, Any],
        entity_id: str = "",
        simulation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a generated A2UI surface. Returns status ok with the surface id,
        or status error with validation issues to fix and retry. Pass `simulation`
        (strategy, extra_payment, extra_income, expense_reduction, horizon_months,
        events) so the plan can be revalidated deterministically on re-fetch."""
        return await service.persist_ui(
            database,
            user_id=user_id,
            domain=domain,
            catalog_id=catalog_id,
            components=components,
            data_model=data_model,
            entity_id=entity_id,
            simulation=simulation,
        )

    @server.tool()
    async def hydrate_ui(surface_id: str) -> dict[str, Any]:
        """Return a persisted surface re-hydrated with fresh data."""
        return await service.hydrate_ui(database, surface_id)

    @server.tool()
    async def a2ui_action(
        user_id: str,
        surface_id: str,
        name: str,
        source_component_id: str = "",
        context: dict[str, Any] | None = None,
        timestamp: str = "",
    ) -> dict[str, Any]:
        """Record a user interaction with a generated component."""
        return await service.a2ui_action(
            database,
            user_id=user_id,
            surface_id=surface_id,
            name=name,
            source_component_id=source_component_id,
            context=context,
            timestamp=timestamp,
        )

    return server
