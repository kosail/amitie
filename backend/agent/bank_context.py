"""Loads `BANK_LOAN_CONTEXT.md`, injected verbatim into the loans consult prompt.

Reads on each call so edits are picked up without a restart; tolerates a missing
or empty file.
"""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = BACKEND_ROOT / "BANK_LOAN_CONTEXT.md"


def load_bank_context(path: Path | None = None) -> str:
    target = path or DEFAULT_PATH
    try:
        return target.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
