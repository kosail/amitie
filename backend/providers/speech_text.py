"""Spoken-form text normalization for TTS.

Some engines — notably the local Piper path, which phonemizes through espeak-ng —
read a digit-grouping separator literally, so `"7,000"` comes out as
"siete, cero cero cero" instead of "siete mil". Stripping the separator leaves a
plain cardinal the engine normalizes itself.

This is applied only to the text handed to the provider. Cache keys and the
stored/displayed text keep the original formatting (`synthesize_speech` in
`mcp_servers/voice/service.py`).
"""

from __future__ import annotations

import re

# A comma between digits that introduces a group of exactly three digits, e.g.
# 7,000 and 1,234,567. Conservative: "12,34" (decimal comma) and "1,2345" are
# left untouched.
_GROUPED = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def normalize_for_speech(text: str) -> str:
    """Return the spoken form of ``text``; idempotent and a no-op on plain text."""
    if not text:
        return ""
    return _GROUPED.sub("", text)
