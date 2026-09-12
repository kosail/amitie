"""Local Piper TTS provider (used silently under PR_SWITCH=1).

Loads a `.onnx` voice from `voices/`, synthesizes 22 kHz mono PCM, and encodes a
real MP3 with `lameenc` so downstream code keeps receiving `audio/mpeg` exactly
like ElevenLabs. Both `piper-tts` and `lameenc` are lazy-imported so the app boots
without them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .base import ProviderResponseError, ProviderUnavailableError
from .voice import SynthesisResult


class PiperTTS:
    name = "piper"

    def __init__(
        self,
        voices_dir: str = "./voices",
        voice: str = "es_MX-claude-high",
    ) -> None:
        self._voices_dir = Path(voices_dir)
        self._default_voice = voice
        self._cache: dict[str, Any] = {}

    def _load(self, voice: str) -> Any:
        if voice in self._cache:
            return self._cache[voice]
        try:
            from piper import PiperVoice
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ProviderUnavailableError("piper-tts is not installed") from exc
        model_path = self._voices_dir / f"{voice}.onnx"
        if not model_path.is_file():
            raise ProviderUnavailableError(f"piper voice not found: {model_path}")
        loaded = PiperVoice.load(str(model_path))
        self._cache[voice] = loaded
        return loaded

    @staticmethod
    def _to_mp3(pcm: bytes, sample_rate: int) -> bytes:
        try:
            import lameenc
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ProviderUnavailableError("lameenc is not installed") from exc
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(128)
        encoder.set_in_sample_rate(sample_rate)
        encoder.set_channels(1)
        encoder.set_quality(2)
        return bytes(encoder.encode(pcm) + encoder.flush())

    @staticmethod
    def _synthesize_pcm(voice_obj: Any, text: str) -> tuple[bytes, int]:
        # piper >= 1.2 yields AudioChunk objects; older versions stream raw PCM.
        if hasattr(voice_obj, "synthesize"):
            pcm = bytearray()
            sample_rate = 22050
            for chunk in voice_obj.synthesize(text):
                sample_rate = getattr(chunk, "sample_rate", sample_rate)
                data = getattr(chunk, "audio_int16_bytes", None)
                if data:
                    pcm.extend(data)
            if pcm:
                return bytes(pcm), int(sample_rate)
        if hasattr(voice_obj, "synthesize_stream_raw"):
            pcm = b"".join(voice_obj.synthesize_stream_raw(text))
            if pcm:
                return pcm, 22050
        raise ProviderResponseError("piper produced no audio")

    async def synthesize(
        self, text: str, voice_id: str = "", speed: float = 1.0
    ) -> SynthesisResult:
        voice = voice_id or self._default_voice

        def run() -> SynthesisResult:
            voice_obj = self._load(voice)
            pcm, sample_rate = self._synthesize_pcm(voice_obj, text)
            return SynthesisResult(
                audio=self._to_mp3(pcm, sample_rate),
                mime="audio/mpeg",
                voice_id=voice,
                provider=self.name,
            )

        try:
            return await asyncio.to_thread(run)
        except (ProviderUnavailableError, ProviderResponseError):
            raise
        except Exception as exc:  # pragma: no cover - runtime/model failure
            raise ProviderUnavailableError(f"piper failed: {exc!r}") from exc
