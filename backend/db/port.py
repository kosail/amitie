"""Persistence port.

Everything that touches SQLite goes through this narrow interface so the rest of
the backend never depends on a concrete driver and can be tested in isolation.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable

Params = Sequence[Any]
Statement = tuple[str, Params]


class DatabaseError(RuntimeError):
    """A query failed."""


@runtime_checkable
class DatabasePort(Protocol):
    @property
    def backend_name(self) -> str: ...

    async def execute(self, sql: str, params: Params = ()) -> None: ...

    async def fetch_all(self, sql: str, params: Params = ()) -> list[dict[str, Any]]: ...

    async def fetch_one(self, sql: str, params: Params = ()) -> dict[str, Any] | None: ...

    async def batch(self, statements: Sequence[Statement]) -> None: ...

    async def close(self) -> None: ...
