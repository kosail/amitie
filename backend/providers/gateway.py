"""Failover wrapper for LLM providers (INV-012).

Tries the primary provider and transparently falls back on quota, rate-limit,
timeout, or network failures. A short cooldown circuit breaker avoids paying the
primary's latency on every call after it starts failing. Every attempt is traced.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from observability.context import current_trace_id
from observability.tracing import TraceEvent, Tracer, new_trace_id

from .base import LLMProvider, LLMResult, Messages, ProviderUnavailableError, Tools

logger = logging.getLogger(__name__)


class FallbackLLM:
    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        *,
        tracer: Tracer | None = None,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._tracer = tracer
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._cooldown_until = 0.0

    @property
    def name(self) -> str:
        return f"{self._primary.name}->{self._fallback.name}"

    @property
    def primary(self) -> LLMProvider:
        return self._primary

    @property
    def fallback(self) -> LLMProvider:
        return self._fallback

    @property
    def model(self) -> str:
        return self._primary.model

    def _primary_ready(self) -> bool:
        return self._clock() >= self._cooldown_until

    async def generate(
        self,
        messages: Messages,
        tools: Tools | None = None,
        response_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        if self._primary_ready():
            try:
                return await self._generate_with(
                    self._primary, messages, tools, response_schema, temperature
                )
            except ProviderUnavailableError as exc:
                self._cooldown_until = self._clock() + self._cooldown_seconds
                logger.warning(
                    "llm failover: %s unavailable (%s); using %s",
                    self._primary.name,
                    exc,
                    self._fallback.name,
                )
        return await self._generate_with(
            self._fallback, messages, tools, response_schema, temperature
        )

    async def _generate_with(
        self,
        provider: LLMProvider,
        messages: Messages,
        tools: Tools | None,
        response_schema: dict[str, Any] | None,
        temperature: float | None,
    ) -> LLMResult:
        started = time.perf_counter()
        result: LLMResult | None = None
        error: str | None = None
        try:
            result = await provider.generate(
                messages,
                tools=tools,
                response_schema=response_schema,
                temperature=temperature,
            )
            return result
        except Exception as exc:
            error = repr(exc)
            raise
        finally:
            await self._trace(
                provider,
                started,
                tokens=result.usage.total_tokens if result is not None else None,
                error=error,
            )

    async def _trace(
        self,
        provider: LLMProvider,
        started: float,
        *,
        tokens: int | None,
        error: str | None,
    ) -> None:
        if self._tracer is None:
            return
        trace_id = current_trace_id() or new_trace_id()
        await self._tracer.record(
            trace_id,
            TraceEvent(
                kind="llm",
                name="generate",
                provider=provider.name,
                model=provider.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                tokens=tokens,
                error=error,
            ),
        )

    async def close(self) -> None:
        for provider in (self._primary, self._fallback):
            close = getattr(provider, "close", None)
            if close is not None:
                await close()
