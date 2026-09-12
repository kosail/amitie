"""Small SQL helpers shared by the schema loader and tests.

Statement splitting is intentionally simple: our DDL contains no semicolons or
`--` sequences inside string literals.
"""

from __future__ import annotations

import re

_LINE_COMMENT = re.compile(r"--[^\n]*")


def strip_sql_comments(sql: str) -> str:
    return _LINE_COMMENT.sub("", sql)


def split_statements(sql: str) -> list[str]:
    cleaned = strip_sql_comments(sql)
    return [statement.strip() for statement in cleaned.split(";") if statement.strip()]
