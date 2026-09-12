"""Local SQLite adapter (the only persistence backend).

Uses the stdlib `sqlite3` module. A single connection is guarded by an asyncio
lock and executed in a worker thread so the port's async contract is honored
without adding an async SQLite dependency.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from .port import DatabaseError, Params, Statement


class LocalSQLiteDatabase:
    backend_name = "local_sqlite"

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        parent = Path(self._path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = asyncio.Lock()

    def _execute_sync(self, sql: str, params: Sequence[Any]) -> None:
        try:
            self._conn.execute(sql, tuple(params))
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise DatabaseError(str(exc)) from exc

    def _fetch_sync(self, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
        try:
            cursor = self._conn.execute(sql, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def _batch_sync(self, statements: Sequence[Statement]) -> None:
        try:
            for sql, params in statements:
                self._conn.execute(sql, tuple(params))
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise DatabaseError(str(exc)) from exc

    async def execute(self, sql: str, params: Params = ()) -> None:
        async with self._lock:
            await asyncio.to_thread(self._execute_sync, sql, params)

    async def fetch_all(self, sql: str, params: Params = ()) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._fetch_sync, sql, params)

    async def fetch_one(self, sql: str, params: Params = ()) -> dict[str, Any] | None:
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    async def batch(self, statements: Sequence[Statement]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._batch_sync, statements)

    async def close(self) -> None:
        self._conn.close()
