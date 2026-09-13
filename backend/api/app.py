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
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from agent.negotiation import NegotiationService
from agent.loans import LoansConsultService
from agent.service import AgentService
from config import Settings, load_dotenv
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from mcp_servers.voice.server import build_voice_server
from observability.logging_config import configure_logging
from observability.middleware import TraceMiddleware
from observability.tracing import Tracer
import structlog

logger = structlog.get_logger(__name__)
from providers.base import LLMProvider
from providers.registry import (
    build_llm_gateway,
    build_research,
    build_stt,
    build_stt_options,
    build_tts,
    build_tts_options,
)
from providers.research import ResearchProvider
from providers.voice import STTProvider, TTSProvider

from .routers import (
    action,
    agent,
    audio,
    auth,
    finance,
    debug,
    loans,
    message,
    negotiation,
    session,
    ui,
    voice,
)


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
    configure_logging(env=resolved.app_env, level=resolved.log_level)
    database = LocalSQLiteDatabase(resolved.database_path)
    tracer = Tracer(database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(env=resolved.app_env, level=resolved.log_level)
        logger.info("backend_started", app_env=resolved.app_env)
        await apply_schema(database)
        research_provider = research or build_research(resolved)
        tts_provider = tts or build_tts(resolved)
        stt_provider = stt or build_stt(resolved)
        resolved_tts_options = (
            tts_options if tts_options is not None else build_tts_options(resolved)
        )
        resolved_stt_options = (
            stt_options if stt_options is not None else build_stt_options(resolved)
        )
        toolbox = InProcessToolbox(
            {
                "finance": build_finance_server(database, resolved),
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
        loans_service = LoansConsultService(
            provider=llm,
            toolbox=toolbox,
            tracer=tracer,
            deadline_seconds=resolved.loans_llm_deadline_seconds,
            max_tokens=resolved.loans_max_tokens,
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
        app.state.loans_service = loans_service
        try:
            yield
        finally:
            await toolbox.__aexit__(None, None, None)
            await database.close()
            logger.info("backend_stopped")

    tags_metadata = [
        {"name": "session", "description": "Gestión de sesiones de usuario."},
        {"name": "auth", "description": "Autenticación y login local de demostración."},
        {"name": "message", "description": "Interacción con el agente y generación de UI A2UI."},
        {"name": "action", "description": "Ejecución de acciones del usuario sobre la interfaz generada."},
        {"name": "loans", "description": "Consulta y análisis de créditos asistidos por voz (Loans & Credits)."},
        {"name": "negotiation", "description": "Simulación y negociación de deuda (El Revés)."},
        {"name": "finance", "description": "Cuentas bancarias, transferencias SPEI, pasivos y abonos."},
        {"name": "ui", "description": "Superficies A2UI dinámicas hidratadas."},
        {"name": "audio", "description": "Activos de audio sintetizados (TTS)."},
        {"name": "debug", "description": "Herramientas de diagnóstico, trazas y pruebas de proveedores."},
    ]

    app = FastAPI(
        title="La Mesa API",
        description="API para La Mesa y El Revés - Asistente Financiero Autónomo con A2UI y MCP",
        version="0.1.0",
        openapi_tags=tags_metadata,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    app.add_middleware(TraceMiddleware, tracer=tracer)

    app.include_router(session.router)
    app.include_router(auth.router)
    app.include_router(message.router)
    app.include_router(agent.router)
    app.include_router(action.router)
    app.include_router(negotiation.router)
    app.include_router(finance.router)
    app.include_router(ui.router)
    app.include_router(audio.router)
    app.include_router(loans.router)
    if resolved.enable_debug_endpoints:
        # Diagnostics only: not part of the frozen frontend contract (INV-023).
        app.include_router(voice.router)
        app.include_router(debug.router)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/swagger")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/swagger", include_in_schema=False)
    @app.get("/swagger/", include_in_schema=False)
    @app.get("/api/swagger", include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=app.openapi_url or "/openapi.json",
            title=f"{app.title} - Swagger UI",
        )

    @app.get("/openapi", include_in_schema=False)
    @app.get("/api/openapi", include_in_schema=False)
    @app.get("/api/openapi.json", include_in_schema=False)
    async def openapi_schema() -> JSONResponse:
        return JSONResponse(content=app.openapi())

    return app
