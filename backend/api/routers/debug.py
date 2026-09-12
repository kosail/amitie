"""Debug endpoints: trace lookup, Kill Test, and provider diagnostics.

`GET /debug/providers` actively probes each configured dependency with a minimal
call so a rehearsal can attribute a failure to a specific vendor (LLM primary /
fallback, research grounding, TTS) rather than guessing.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from mcp_servers.toolbox import Toolbox
from observability.tracing import Tracer
from providers.base import ChatMessage, LLMProvider
from providers.gateway import FallbackLLM
from providers.research import ResearchProvider
from providers.voice import STTProvider, TTSProvider

from ..dependencies import (
    get_llm,
    get_research,
    get_stt,
    get_toolbox,
    get_tracer,
    get_tts,
)
from ..schemas import HttpErrorDetail, ProviderHealth, ProvidersResponse, TraceResponse, UiResponse

router = APIRouter(tags=["debug"])

_LLM_PROMPT = "Responde únicamente con la palabra: pong"
_RESEARCH_QUERY = "costo promedio en MXN de un vuelo redondo a Japón desde CDMX"
_TTS_TEXT = "Hola, esta es una prueba de voz de La Mesa."
_PROBE_TIMEOUT = 25.0


def _entry(name: str, provider: Any, started: float, **extra: Any) -> ProviderHealth:
    return ProviderHealth(
        name=name,
        provider=getattr(provider, "name", None),
        model=getattr(provider, "model", None),
        latency_ms=int((time.perf_counter() - started) * 1000),
        **extra,
    )


async def _probe_llm(name: str, provider: LLMProvider) -> ProviderHealth:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            provider.generate([ChatMessage(role="user", content=_LLM_PROMPT)], temperature=0.0),
            timeout=_PROBE_TIMEOUT,
        )
        return _entry(name, provider, started, ok=True, detail=(result.text or "").strip()[:80])
    except Exception as exc:  # diagnostic: report, never raise
        return _entry(name, provider, started, ok=False, error=f"{type(exc).__name__}: {exc}")


async def _probe_research(provider: ResearchProvider) -> ProviderHealth:
    started = time.perf_counter()
    try:
        snapshot = await asyncio.wait_for(
            provider.research(_RESEARCH_QUERY), timeout=_PROBE_TIMEOUT
        )
        return _entry("research", provider, started, ok=True, detail=snapshot.source)
    except Exception as exc:
        return _entry("research", provider, started, ok=False, error=f"{type(exc).__name__}: {exc}")


async def _probe_tts(provider: TTSProvider) -> ProviderHealth:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            provider.synthesize(_TTS_TEXT, "", 1.0), timeout=_PROBE_TIMEOUT
        )
        return _entry(
            "tts",
            provider,
            started,
            ok=True,
            detail=f"{len(result.audio)} bytes via {result.provider}",
        )
    except Exception as exc:
        return _entry("tts", provider, started, ok=False, error=f"{type(exc).__name__}: {exc}")


def _probe_stt(provider: STTProvider) -> ProviderHealth:
    return ProviderHealth(
        name="stt",
        provider=getattr(provider, "name", None),
        ok=None,
        detail="configured (a real probe needs audio input)",
    )


@router.get(
    "/debug/trace/{trace_id}",
    response_model=TraceResponse,
    summary="Fetch structured traces (REQ-API-08, REQ-NFR-02)",
    response_description="Chronological trace events including latency, model, tokens, and tool calls",
    operation_id="get_trace",
    responses={
        200: {
            "description": "Trace events retrieved from SQLite observability table.",
            "model": TraceResponse,
        },
    },
)
async def get_trace(trace_id: str, tracer: Tracer = Depends(get_tracer)) -> TraceResponse:
    """Retrieve full structured trace records for a given request trace_id (INV-018)."""
    events = await tracer.history(trace_id)
    return TraceResponse(trace_id=trace_id, events=events)


@router.get(
    "/debug/kill-test/{surface_id}",
    response_model=UiResponse,
    summary="Serve frozen Kill Test UI (REQ-API-08, REQ-KT-01)",
    response_description="Persisted UI with frozen data and zero agent execution",
    operation_id="get_kill_test",
    responses={
        200: {
            "description": "Frozen UI artifact served successfully without LLM involvement.",
            "model": UiResponse,
        },
        404: {
            "description": "Frozen artifact not found for this surface.",
            "model": HttpErrorDetail,
        },
    },
)
async def get_kill_test(
    surface_id: str, toolbox: Toolbox = Depends(get_toolbox)
) -> UiResponse:
    """Serve a persisted surface from its genuine frozen artifact, with no agent
    and no live recomputation (REQ-KT-01, REQ-KT-02, INV-032). Proves the interface
    collapses without the real-time agent."""
    result = await toolbox.call("kill_test", {"surface_id": surface_id})
    if result.get("status") != "ok":
        detail = "; ".join(result.get("issues") or ["no frozen artifact"])
        raise HTTPException(status_code=404, detail=detail)
    return UiResponse(
        status="ok",
        surface_id=surface_id,
        a2ui=result.get("a2ui", []),
        catalog_id=result.get("catalog_id"),
        audio_ref=result.get("audio_ref"),
    )


@router.get("/debug/providers", response_model=ProvidersResponse)
async def get_providers(
    llm: LLMProvider = Depends(get_llm),
    research: ResearchProvider = Depends(get_research),
    tts: TTSProvider = Depends(get_tts),
    stt: STTProvider = Depends(get_stt),
) -> ProvidersResponse:
    """Probe every configured provider with a minimal real call."""
    providers: list[ProviderHealth] = []
    if isinstance(llm, FallbackLLM):
        providers.append(await _probe_llm("llm.primary", llm.primary))
        providers.append(await _probe_llm("llm.fallback", llm.fallback))
    else:
        providers.append(await _probe_llm("llm", llm))
    providers.append(await _probe_research(research))
    providers.append(await _probe_tts(tts))
    providers.append(_probe_stt(stt))
    return ProvidersResponse(status="ok", providers=providers)
