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
    await _ensure_columns(database)


async def _ensure_columns(database: DatabasePort) -> None:
    """Idempotent lightweight migrations for local SQLite databases."""
    rows = await database.fetch_all("PRAGMA table_info(generated_ui)")
    columns = {row["name"] for row in rows}
    if "frozen_json" not in columns:
        await database.execute("ALTER TABLE generated_ui ADD COLUMN frozen_json TEXT")

    user_columns = {row["name"] for row in await database.fetch_all("PRAGMA table_info(users)")}
    if "username" not in user_columns:
        await database.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "password_hash" not in user_columns:
        await database.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if "password_salt" not in user_columns:
        await database.execute("ALTER TABLE users ADD COLUMN password_salt TEXT")
    if "education_level" not in user_columns:
        await database.execute("ALTER TABLE users ADD COLUMN education_level TEXT")
    await database.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"
    )

    liability_columns = {
        row["name"] for row in await database.fetch_all("PRAGMA table_info(liabilities)")
    }
    for name, ddl in (
        ("term_months", "INTEGER"),
        ("opening_fee", "REAL DEFAULT 0"),
        ("insurance_fee", "REAL DEFAULT 0"),
        ("cat", "REAL DEFAULT 0"),
    ):
        if name not in liability_columns:
            await database.execute(f"ALTER TABLE liabilities ADD COLUMN {name} {ddl}")
    transaction_columns = {
        row["name"] for row in await database.fetch_all("PRAGMA table_info(transactions)")
    }
    if "memo" not in transaction_columns:
        await database.execute("ALTER TABLE transactions ADD COLUMN memo TEXT")
