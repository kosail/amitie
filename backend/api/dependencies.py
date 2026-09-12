"""Dependency injection accessors.

Everything is resolved from `app.state`, which the lifespan populates, so tests
can build the app with an injected provider and no network.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request

from agent.negotiation import NegotiationService
from agent.service import AgentService
from db.port import DatabasePort
from mcp_servers.toolbox import Toolbox
from observability.tracing import Tracer
from providers.base import LLMProvider
from providers.research import ResearchProvider
from providers.voice import STTProvider, TTSProvider


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


def get_negotiation_service(request: Request) -> NegotiationService:
    return request.app.state.negotiation_service


def get_llm(request: Request) -> LLMProvider:
    return request.app.state.llm


def get_research(request: Request) -> ResearchProvider:
    return request.app.state.research


def get_tts(request: Request) -> TTSProvider:
    return request.app.state.tts


def get_stt(request: Request) -> STTProvider:
    return request.app.state.stt
