"""Voice service: TTS synthesis with caching and STT transcription.

Audio assets are cached by text hash in `audio_assets` plus a file under the
audio cache directory (REQ-ACC-05). Every surface in accessible mode gets one.
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from db.port import DatabasePort
from providers.base import ProviderError
from providers.speech_text import normalize_for_speech
from providers.voice import STTProvider, TTSProvider

_EXTENSIONS = {"audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/ogg": ".ogg"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def text_hash(text: str, voice_id: str = "", speed: float = 1.0) -> str:
    """Stable cache key. Primarily the text, plus voice/speed so different voices don't collide."""
    material = f"{text.strip()}|{voice_id}|{round(float(speed), 3)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _audio_ref(asset_id: str) -> str:
    return f"/api/audio/{asset_id}"


async def _cached(database: DatabasePort, digest: str) -> dict[str, Any] | None:
    row = await database.fetch_one(
        "SELECT id, text, voice_id, file_path FROM audio_assets "
        "WHERE text_hash = ? ORDER BY created_at DESC LIMIT 1",
        (digest,),
    )
    if row is None:
        return None
    file_path = row["file_path"]
    if file_path and Path(file_path).is_file():
        return row
    return None


async def synthesize_speech(
    database: DatabasePort,
    tts: TTSProvider,
    *,
    text: str,
    user_id: str,
    surface_id: str = "",
    voice_id: str = "",
    speed: float = 1.0,
    cache_dir: str = "./audio_cache",
) -> dict[str, Any]:
    clean = (text or "").strip()
    if not clean:
        return {"status": "error", "issues": ["speech text is empty"]}

    digest = text_hash(clean, voice_id, speed)
    cached = await _cached(database, digest)
    if cached is not None:
        return {
            "status": "ok",
            "audio_id": cached["id"],
            "audio_ref": _audio_ref(cached["id"]),
            "cached": True,
            "voice_id": cached["voice_id"],
            "provider": "cache",
            "mime": mimetypes.guess_type(cached["file_path"] or "")[0] or "audio/mpeg",
        }

    try:
        result = await tts.synthesize(normalize_for_speech(clean), voice_id, speed)
    except ProviderError as exc:
        return {"status": "unavailable", "reason": str(exc), "text": clean}

    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    asset_id = "aud_" + uuid.uuid4().hex[:12]
    extension = _EXTENSIONS.get(result.mime, Path(mimetypes.guess_extension(result.mime) or ".bin").suffix)
    file_path = cache_path / f"{asset_id}{extension}"
    file_path.write_bytes(result.audio)

    await database.execute(
        "INSERT INTO audio_assets (id, user_id, surface_id, text, text_hash, voice_id, "
        "file_path, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (
            asset_id,
            user_id or None,
            surface_id or None,
            clean,
            digest,
            result.voice_id,
            str(file_path),
            _now(),
        ),
    )
    return {
        "status": "ok",
        "audio_id": asset_id,
        "audio_ref": _audio_ref(asset_id),
        "cached": False,
        "voice_id": result.voice_id,
        "provider": result.provider,
        "mime": result.mime,
    }


async def transcribe_audio(
    database: DatabasePort,
    stt: STTProvider,
    *,
    audio_b64: str,
    language: str = "es-MX",
    mime: str = "audio/mpeg",
) -> dict[str, Any]:
    try:
        audio = base64.b64decode(audio_b64, validate=True)
    except (ValueError, TypeError):
        return {"status": "error", "issues": ["audio_b64 is not valid base64"]}
    if not audio:
        return {"status": "error", "issues": ["audio payload is empty"]}

    try:
        result = await stt.transcribe(audio, mime, language)
    except ProviderError as exc:
        return {"status": "error", "issues": [str(exc)]}
    return {
        "status": "ok",
        "text": result.text,
        "provider": result.provider,
        "language": result.language,
    }


async def get_audio(database: DatabasePort, asset_id: str) -> dict[str, Any]:
    row = await database.fetch_one(
        "SELECT id, user_id, surface_id, text, voice_id, file_path, created_at "
        "FROM audio_assets WHERE id = ?",
        (asset_id,),
    )
    if row is None:
        return {"status": "error", "issues": [f"unknown audio asset {asset_id!r}"]}
    return {
        "status": "ok",
        "audio_id": row["id"],
        "user_id": row["user_id"],
        "surface_id": row["surface_id"],
        "text": row["text"],
        "voice_id": row["voice_id"],
        "file_path": row["file_path"],
    }
