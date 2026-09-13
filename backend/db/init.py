"""Create and seed the local SQLite database.

Usage (from backend/):
    python -m db.init
    python -m db.init --path ./data/amitie.sqlite3

Re-running is safe: the schema is `IF NOT EXISTS` and the seed clears and
rebuilds the showcase tables.
"""

from __future__ import annotations

import argparse
import asyncio

from config import Settings, load_dotenv
import structlog

from .local_sqlite import LocalSQLiteDatabase
from .schema import apply_schema
from .seed import seed

logger = structlog.get_logger(__name__)


async def initialize(database_path: str) -> None:
    database = LocalSQLiteDatabase(database_path)
    try:
        await apply_schema(database)
        await seed(database)
    finally:
        await database.close()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Initialize the local La Mesa database.")
    parser.add_argument("--path", default=None, help="SQLite file path (defaults to DATABASE_PATH)")
    args = parser.parse_args()

    database_path = args.path or Settings.from_env().database_path
    asyncio.run(initialize(database_path))
    logger.info("database_initialized", database_path=database_path)


if __name__ == "__main__":
    main()
