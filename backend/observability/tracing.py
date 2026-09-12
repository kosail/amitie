"""Trace persistence. Every LLM call and MCP tool call is recorded and retrievable.

Backed by the `traces` table so `/debug/trace/{trace_id}` can reconstruct a
request without reading logs (INV-018).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from db.port import DatabasePort


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TraceEvent:
    kind: str
    name: str
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    tokens: int | None = None
    error: str | None = None
    payload: dict[str, Any] | None = None


class Tracer:
    def __init__(self, database: DatabasePort) -> None:
        self._database = database

    async def record(
        self, trace_id: str, event: TraceEvent, parent_id: str | None = None
    ) -> str:
        record_id = uuid.uuid4().hex
        await self._database.execute(
            "INSERT INTO traces (id, trace_id, parent_id, kind, name, provider, model, "
            "latency_ms, tokens, error, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                trace_id,
                parent_id,
                event.kind,
                event.name,
                event.provider,
                event.model,
                event.latency_ms,
                event.tokens,
                event.error,
                json.dumps(event.payload or {}, separators=(",", ":")),
                _now(),
            ),
        )
        return record_id

    async def history(self, trace_id: str) -> list[dict[str, Any]]:
        return await self._database.fetch_all(
            "SELECT id, trace_id, parent_id, kind, name, provider, model, latency_ms, "
            "tokens, error, payload_json, created_at FROM traces "
            "WHERE trace_id = ? ORDER BY created_at, id",
            (trace_id,),
        )
