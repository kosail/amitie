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
        speech: str = "",
    ) -> dict[str, Any]:
        """Persist a generated A2UI surface. Returns status ok with the surface id,
        or status error with validation issues to fix and retry. Pass `simulation`
        (strategy, extra_payment, extra_income, expense_reduction, horizon_months,
        events) so the plan can be revalidated deterministically on re-fetch. Pass
        `speech` with the spoken summary when the user is in accessible mode
        (the catalog and audio are handled automatically)."""
        return await service.persist_ui(
            database,
            user_id=user_id,
            domain=domain,
            catalog_id=catalog_id,
            components=components,
            data_model=data_model,
            entity_id=entity_id,
            simulation=simulation,
            speech=speech,
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

    @server.tool()
    async def record_negotiation_round(
        session_id: str, actor: str, offer: dict[str, Any]
    ) -> dict[str, Any]:
        """Record one El Reves negotiation round (actor bank/advocate/user)."""
        return await service.record_negotiation_round(
            database, session_id=session_id, actor=actor, offer=offer
        )

    @server.tool()
    async def get_negotiation(session_id: str) -> dict[str, Any]:
        """Return the recorded negotiation rounds for a session."""
        return await service.get_negotiation(database, session_id)

    @server.tool()
    async def get_session(session_id: str) -> dict[str, Any]:
        """Return a session row and its context."""
        return await service.get_session(database, session_id)

    @server.tool()
    async def set_session_context(session_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Merge fields into a session's context (used for negotiation state)."""
        return await service.set_session_context(database, session_id, context)

    return server
