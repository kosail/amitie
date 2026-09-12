"""Schema access. `db/schema.sql` is the single source of truth."""

from __future__ import annotations

from pathlib import Path

from .port import DatabasePort
from .sql_utils import split_statements

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def schema_statements() -> list[str]:
    return split_statements(SCHEMA_PATH.read_text(encoding="utf-8"))


async def apply_schema(database: DatabasePort) -> None:
    await database.batch([(statement, ()) for statement in schema_statements()])
