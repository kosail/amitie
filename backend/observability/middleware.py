"""Framework-agnostic ASGI middleware that assigns and records a trace id.

No web-framework dependency: it speaks raw ASGI, so it can be mounted on the
FastAPI app later without coupling observability to FastAPI.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

import structlog

from .context import trace_context
from .tracing import TraceEvent, Tracer, new_trace_id

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class TraceMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]], tracer: Tracer) -> None:
        self._app = app
        self._tracer = tracer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        headers_raw = dict(scope.get("headers") or [])
        header_trace = headers_raw.get(b"x-trace-id", b"").decode("latin1", errors="ignore").strip()
        trace_id = header_trace or new_trace_id()
        started = time.perf_counter()
        status = {"code": 0}

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            path=scope.get("path", ""),
            method=scope.get("method", ""),
        )

        async def send_with_trace(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers") or [])
                headers.append((b"x-trace-id", trace_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        error: str | None = None
        with trace_context(trace_id):
            try:
                await self._app(scope, receive, send_with_trace)
            except Exception as exc:
                error = repr(exc)
                raise
            finally:
                await self._tracer.record(
                    trace_id,
                    TraceEvent(
                        kind="http",
                        name=scope.get("path", ""),
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        error=error,
                        payload={
                            "method": scope.get("method"),
                            "status": status["code"],
                        },
                    ),
                )
                structlog.contextvars.clear_contextvars()
