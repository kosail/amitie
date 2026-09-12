"""Provider selection from configuration (INV-013: env-only swaps)."""

from __future__ import annotations

from dataclasses import replace

from config import Settings

from .base import LLMProvider
from .gateway import FallbackLLM


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
