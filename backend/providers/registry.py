"""Provider selection from configuration (INV-013: env-only swaps)."""

from __future__ import annotations

from dataclasses import replace

from config import Settings

from .base import LLMProvider
from .gateway import FallbackLLM
from .research import FallbackResearch, ResearchProvider, StaticPriceTableResearch


def build_llm(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider
    if provider == "gemini":
        from .gemini import GeminiLLM

        return GeminiLLM(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if provider == "deepseek":
        from .deepseek import DeepSeekLLM

        return DeepSeekLLM(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            thinking=settings.deepseek_thinking,
        )
    raise ValueError(f"unknown LLM_PROVIDER: {provider!r}")


def build_llm_gateway(settings: Settings, tracer: object | None = None) -> LLMProvider:
    primary = build_llm(settings)
    fallback_name = settings.llm_fallback
    if not fallback_name or fallback_name == settings.llm_provider:
        return primary
    fallback = build_llm(replace(settings, llm_provider=fallback_name))
    return FallbackLLM(
        primary,
        fallback,
        tracer=tracer,  # type: ignore[arg-type]
        cooldown_seconds=settings.llm_failover_cooldown_seconds,
    )


def _build_research_provider(settings: Settings, name: str) -> ResearchProvider:
    if name in ("static_table", "static", "static_prices"):
        return StaticPriceTableResearch()
    if name == "gemini_grounding":
        from .research import GeminiGroundingResearch

        return GeminiGroundingResearch(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.research_timeout_seconds,
        )
    raise ValueError(f"unknown research provider: {name!r}")


def build_research(settings: Settings) -> ResearchProvider:
    provider_name = settings.research_provider
    fallback_name = settings.research_fallback
    if provider_name == "gemini_grounding" and not settings.gemini_api_key:
        provider_name = fallback_name or "static_table"
    primary = _build_research_provider(settings, provider_name)
    if not fallback_name or fallback_name == provider_name:
        return primary
    fallback = _build_research_provider(settings, fallback_name)
    return FallbackResearch(primary, fallback)
