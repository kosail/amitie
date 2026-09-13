"""Spoken-form text normalization for TTS.

Some engines — notably the local Piper path, which phonemizes through espeak-ng —
read formatted numbers literally: `"7,000"` comes out as "siete coma cero cero
cero" and `"$1,000.00"` as "dólar mil punto cero cero". Rewriting the text into
its Spanish spoken form ("siete mil", "mil pesos") lets any engine pronounce it
naturally.

This is applied only to the text handed to the provider and to the cache key.
The stored/displayed text keeps the original formatting (`synthesize_speech` in
`mcp_servers/voice/service.py`).
"""

from __future__ import annotations

import re

# A grouped or plain number, e.g. 7,000 / 1,234,567 / 1000 / 1000.50.
_NUMBER = r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?"

# Numeric ranges only, so prose dashes ("La Mesa — una app") are left alone.
_RANGE = re.compile(r"(?<=[\d%])\s*[–—]\s*(?=\$?\d)")
_TRAILING_ZERO = re.compile(r"(?<=\d)\.00(?!\d)")
# `$1,000`, `$1,000 MXN`, `$1,000 pesos` all become `1,000 pesos` (no duplication).
_CURRENCY = re.compile(r"\$\s*(" + _NUMBER + r")(?:\s+(?:pesos|MXN))?")
_MXN = re.compile(r"\bMXN\b")
_DUPLICATE_PESOS = re.compile(r"\bpesos\s+pesos\b")
# A comma between digits that introduces a group of exactly three digits.
_GROUPED = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_SPACES = re.compile(r"\s{2,}")


def normalize_for_speech(text: str) -> str:
    """Return the spoken form of ``text``; idempotent and a no-op on plain text."""
    if not text:
        return ""
    spoken = _RANGE.sub(" a ", text)
    spoken = _TRAILING_ZERO.sub("", spoken)
    spoken = _CURRENCY.sub(r"\1 pesos", spoken)
    spoken = _MXN.sub("pesos", spoken)
    spoken = _DUPLICATE_PESOS.sub("pesos", spoken)
    spoken = _GROUPED.sub("", spoken)
    return _SPACES.sub(" ", spoken).strip()
