"""Savings MCP server: Saving Bags data, research, and deterministic math."""

from __future__ import annotations

from typing import Any

from db.port import DatabasePort
from mcp.server import MCPServer
from providers.research import ResearchProvider

from . import service


def build_savings_server(database: DatabasePort, research: ResearchProvider) -> MCPServer:
    server = MCPServer("savings")

    @server.tool()
    async def create_bag(
        user_id: str,
        name: str,
        target_amount: float | None = None,
        target_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a saving bag by name, optionally with a goal amount and date."""
        return await service.create_bag(
            database,
            user_id=user_id,
            name=name,
            target_amount=target_amount,
            target_date=target_date,
        )

    @server.tool()
    async def get_bag(bag_id: str) -> dict[str, Any]:
        """Return a saving bag by id."""
        bag = await service.get_bag(database, bag_id)
        return {"status": "ok", "bag": bag} if bag else {"status": "error", "issues": ["unknown bag"]}

    @server.tool()
    async def list_bags(user_id: str) -> dict[str, Any]:
        """List a user's saving bags."""
        return {"status": "ok", "bags": await service.list_bags(database, user_id)}

    @server.tool()
    async def answer_bag(bag_id: str, answers: list[dict[str, Any]]) -> dict[str, Any]:
        """Persist the user's answers to the inferred question set."""
        return await service.answer_bag(database, bag_id, answers)

    @server.tool()
    async def research_costs(bag_id: str, query: str = "") -> dict[str, Any]:
        """Research real average costs and store an immutable snapshot. Call only
        when creating the bag or on an explicit refresh."""
        return await service.research_costs(database, bag_id, research, query=query or None)

    @server.tool()
    async def estimate_total(bag_id: str) -> dict[str, Any]:
        """Deterministically estimate the total cost from the latest snapshot + answers."""
        return await service.estimate_total(database, bag_id)

    @server.tool()
    async def compute_feasibility(bag_id: str, goal_reduced: bool = False) -> dict[str, Any]:
        """Compute the dated funding plan from the user's real cash flow and persist it."""
        return await service.compute_feasibility(database, bag_id, goal_reduced=goal_reduced)

    @server.tool()
    async def refresh_bag(bag_id: str) -> dict[str, Any]:
        """Re-run research (new snapshot) and recompute feasibility."""
        return await service.refresh_bag(database, bag_id, research)

    @server.tool()
    async def get_savings_snapshot(bag_id: str) -> dict[str, Any]:
        """Return the full saving-bag state (bag, answers, research, estimate, plan)."""
        snapshot = await service.savings_snapshot(database, bag_id)
        return (
            {"status": "ok", "savings": snapshot}
            if snapshot
            else {"status": "error", "issues": ["unknown bag"]}
        )

    return server
