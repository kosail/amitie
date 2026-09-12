"""Provider selection from configuration (INV-013: env-only swaps)."""

from __future__ import annotations

from dataclasses import replace

from config import Settings

from .base import LLMProvider
from .gateway import FallbackLLM
from .research import FallbackResearch, ResearchProvider, StaticPriceTableResearch
from .voice import FallbackSTT, FallbackTTS, NullSTT, NullTTS, STTProvider, TTSProvider


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


def build_tts_provider(settings: Settings, name: str) -> TTSProvider:
    if name in ("edge_tts", "edge-tts", "edge"):
        from .voice import EdgeTTS

        return EdgeTTS(settings.edge_tts_voice)
    if name == "elevenlabs":
        from .voice import ElevenLabsTTS

        return ElevenLabsTTS(
            api_key=settings.elevenlabs_api_key,
            model=settings.elevenlabs_model,
            default_voice_id=settings.elevenlabs_voice_id,
        )
    if name in ("none", "null", ""):
        return NullTTS()
    raise ValueError(f"unknown TTS provider: {name!r}")


def build_tts(
    settings: Settings, *, provider: str | None = None, fallback: str | None = None
) -> TTSProvider:
    name = provider or settings.tts_provider
    fallback_name = settings.tts_fallback if fallback is None else fallback
    if name == "elevenlabs" and not settings.elevenlabs_api_key:
        name = fallback_name or "edge_tts"
    primary = build_tts_provider(settings, name)
    if not fallback_name or fallback_name == name:
        return primary
    return FallbackTTS(primary, build_tts_provider(settings, fallback_name))


def build_stt_provider(settings: Settings, name: str) -> STTProvider:
    if name == "gemini":
        from .voice import GeminiSTT

        return GeminiSTT(api_key=settings.gemini_api_key, model=settings.stt_model)
    if name in ("faster_whisper", "faster-whisper", "whisper"):
        from .voice import FasterWhisperSTT

        return FasterWhisperSTT(settings.whisper_model)
    if name in ("none", "null", ""):
        return NullSTT()
    raise ValueError(f"unknown STT provider: {name!r}")


def build_stt(
    settings: Settings, *, provider: str | None = None, fallback: str | None = None
) -> STTProvider:
    name = provider or settings.stt_provider
    fallback_name = settings.stt_fallback if fallback is None else fallback
    if name == "gemini" and not settings.gemini_api_key:
        name = fallback_name or "faster_whisper"
    primary = build_stt_provider(settings, name)
    if not fallback_name or fallback_name == name:
        return primary
    return FallbackSTT(primary, build_stt_provider(settings, fallback_name))
