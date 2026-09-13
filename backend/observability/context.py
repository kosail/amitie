"""Per-request trace context."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import structlog

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def current_trace_id() -> str | None:
    return _trace_id.get()


@contextmanager
def trace_context(trace_id: str) -> Iterator[str]:
    token = _trace_id.set(trace_id)
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    try:
        yield trace_id
    finally:
        _trace_id.reset(token)
