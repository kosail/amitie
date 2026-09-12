"""FastAPI application factory.

The database and tracer are created eagerly (so `TraceMiddleware` can be
mounted); the MCP toolbox and agent are built in the lifespan, where async
setup is allowed.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.negotiation import NegotiationService
from agent.service import AgentService
from config import Settings, load_dotenv
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from mcp_servers.finance.server import build_finance_server
from mcp_servers.savings.server import build_savings_server
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from mcp_servers.voice.server import build_voice_server
from observability.middleware import TraceMiddleware
from observability.tracing import Tracer
from providers.base import LLMProvider
from providers.registry import (
    build_llm_gateway,
    build_research,
    build_stt,
    build_stt_provider,
    build_tts,
    build_tts_provider,
)
from providers.research import ResearchProvider
from providers.voice import STTProvider, TTSProvider

from .routers import (
    action,
    audio,
    debug,
    message,
    negotiation,
    saving_bags,
    session,
    ui,
    voice,
)


def _provider_options(settings: Settings, names: tuple[str, ...], builder) -> dict:
    """Build individually-addressable providers so an endpoint can force one."""
    options: dict = {}
    for name in names:
        try:
            options[name] = builder(settings, name)
        except Exception:
            continue
    return options


def create_app(
    *,
    provider: LLMProvider | None = None,
    settings: Settings | None = None,
    research: ResearchProvider | None = None,
    tts: TTSProvider | None = None,
    stt: STTProvider | None = None,
    tts_options: dict[str, TTSProvider] | None = None,
    stt_options: dict[str, STTProvider] | None = None,
) -> FastAPI:
    load_dotenv()
    resolved = settings or Settings.from_env()
    database = LocalSQLiteDatabase(resolved.database_path)
    tracer = Tracer(database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await apply_schema(database)
        research_provider = research or build_research(resolved)
        tts_provider = tts or build_tts(resolved)
        stt_provider = stt or build_stt(resolved)
        resolved_tts_options = tts_options if tts_options is not None else _provider_options(
            resolved, ("elevenlabs", "edge_tts"), build_tts_provider
        )
        resolved_stt_options = stt_options if stt_options is not None else _provider_options(
            resolved, ("gemini", "faster_whisper"), build_stt_provider
        )
        toolbox = InProcessToolbox(
            {
                "finance": build_finance_server(database),
                "savings": build_savings_server(database, research_provider),
                "ui": build_ui_server(database),
                "voice": build_voice_server(
                    database,
                    tts_provider,
                    stt_provider,
                    tts_options=resolved_tts_options,
                    stt_options=resolved_stt_options,
                    cache_dir=resolved.audio_cache_dir,
                ),
            }
        )
        await toolbox.__aenter__()
        llm = provider or build_llm_gateway(resolved, tracer=tracer)
        agent_service = AgentService(
            provider=llm,
            toolbox=toolbox,
            tracer=tracer,
            max_model_calls=resolved.agent_max_model_calls,
        )
        negotiation_service = NegotiationService(
            provider=llm,
            toolbox=toolbox,
            tracer=tracer,
            max_model_calls=resolved.agent_max_model_calls,
        )
        app.state.settings = resolved
        app.state.database = database
        app.state.tracer = tracer
        app.state.toolbox = toolbox
        app.state.llm = llm
        app.state.research = research_provider
        app.state.tts = tts_provider
        app.state.stt = stt_provider
        app.state.agent_service = agent_service
        app.state.negotiation_service = negotiation_service
        try:
            yield
        finally:
            await toolbox.__aexit__(None, None, None)
            await database.close()

    app = FastAPI(title="La Mesa API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    app.add_middleware(TraceMiddleware, tracer=tracer)

    app.include_router(session.router)
    app.include_router(message.router)
    app.include_router(action.router)
    app.include_router(negotiation.router)
    app.include_router(saving_bags.router)
    app.include_router(ui.router)
    app.include_router(audio.router)
    if resolved.enable_debug_endpoints:
        # Diagnostics only: not part of the frozen frontend contract (INV-023).
        app.include_router(voice.router)
        app.include_router(debug.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
