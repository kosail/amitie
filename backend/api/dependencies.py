"""Dependency injection accessors.

Everything is resolved from `app.state`, which the lifespan populates, so tests
can build the app with an injected provider and no network.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request

from agent.service import AgentService
from db.port import DatabasePort
from mcp_servers.toolbox import Toolbox
from observability.tracing import Tracer


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_database(request: Request) -> DatabasePort:
    return request.app.state.database


def get_tracer(request: Request) -> Tracer:
    return request.app.state.tracer


def get_toolbox(request: Request) -> Toolbox:
    return request.app.state.toolbox


def get_agent_service(request: Request) -> AgentService:
    return request.app.state.agent_service
