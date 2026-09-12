"""Voice providers: TTS and STT chains (INV-012, INV-013).

TTS: ElevenLabs (primary) -> edge-tts (fallback).
STT: Gemini multimodal (primary) -> faster-whisper (fallback).

Both are env-selected and lazy: the heavy/optional SDKs are imported only when a
provider is actually used, so the app boots and tests run without them. `Null*`
providers raise a clear `ProviderUnavailableError` when nothing is configured,
letting callers degrade to text-only.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .base import ProviderError, ProviderResponseError, ProviderUnavailableError


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    mime: str
    voice_id: str
    provider: str


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    provider: str
    language: str


@runtime_checkable
class TTSProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def synthesize(
        self, text: str, voice_id: str = "", speed: float = 1.0
    ) -> SynthesisResult: ...


@runtime_checkable
class STTProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def transcribe(
        self, audio: bytes, mime: str = "audio/mpeg", language: str = "es-MX"
    ) -> TranscriptionResult: ...


class ElevenLabsTTS:
    name = "elevenlabs"

    def __init__(
        self,
        api_key: str,
        model: str = "eleven_multilingual_v2",
        default_voice_id: str = "",
        *,
        base_url: str = "https://api.elevenlabs.io",
        timeout: float = 30.0,
        client: Any | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("ELEVENLABS_API_KEY is required for the elevenlabs provider")
        if client is None:
            import httpx2

            client = httpx2.AsyncClient(timeout=timeout)
        self._client = client
        self._api_key = api_key
        self._model = model
        self._default_voice = default_voice_id
        self._base_url = base_url.rstrip("/")
        self._owns_client = True

    async def synthesize(
        self, text: str, voice_id: str = "", speed: float = 1.0
    ) -> SynthesisResult:
        import httpx2

        voice = voice_id or self._default_voice
        if not voice:
            raise ProviderUnavailableError("no ElevenLabs voice id configured")
        payload: dict[str, Any] = {"text": text, "model_id": self._model}
        settings: dict[str, Any] = {"stability": 0.4, "similarity_boost": 0.75}
        if speed and abs(speed - 1.0) > 1e-6:
            settings["speed"] = speed
        payload["voice_settings"] = settings
        try:
            response = await self._client.post(
                f"{self._base_url}/v1/text-to-speech/{voice}",
                headers={
                    "xi-api-key": self._api_key,
                    "accept": "audio/mpeg",
                    "content-type": "application/json",
                },
                json=payload,
            )
        except httpx2.HTTPError as exc:
            raise ProviderUnavailableError(f"elevenlabs request failed: {exc!r}") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderUnavailableError(
                f"elevenlabs unavailable ({response.status_code})"
            )
        if response.status_code >= 400:
            raise ProviderResponseError(f"elevenlabs error ({response.status_code})")
        return SynthesisResult(
            audio=response.content, mime="audio/mpeg", voice_id=voice, provider=self.name
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class EdgeTTS:
    name = "edge_tts"

    def __init__(self, default_voice: str = "es-MX-DaliaNeural") -> None:
        self._default_voice = default_voice or "es-MX-DaliaNeural"

    async def synthesize(
        self, text: str, voice_id: str = "", speed: float = 1.0
    ) -> SynthesisResult:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ProviderUnavailableError("edge-tts is not installed") from exc

        voice = voice_id or self._default_voice
        rate = f"{int(round((speed - 1.0) * 100)):+d}%" if speed else "+0%"
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        chunks = bytearray()
        try:
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.extend(chunk["data"])
        except Exception as exc:  # pragma: no cover - network/library failure
            raise ProviderUnavailableError(f"edge-tts failed: {exc!r}") from exc
        if not chunks:
            raise ProviderResponseError("edge-tts returned no audio")
        return SynthesisResult(
            audio=bytes(chunks), mime="audio/mpeg", voice_id=voice, provider=self.name
        )


class NullTTS:
    name = "none"

    async def synthesize(
        self, text: str, voice_id: str = "", speed: float = 1.0
    ) -> SynthesisResult:
        raise ProviderUnavailableError("no TTS provider is configured")


class FallbackTTS:
    def __init__(self, primary: TTSProvider, fallback: TTSProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def name(self) -> str:
        return f"{self._primary.name}->{self._fallback.name}"

    async def synthesize(
        self, text: str, voice_id: str = "", speed: float = 1.0
    ) -> SynthesisResult:
        try:
            return await self._primary.synthesize(text, voice_id, speed)
        except ProviderError:
            return await self._fallback.synthesize(text, voice_id, speed)

    async def close(self) -> None:
        for provider in (self._primary, self._fallback):
            close = getattr(provider, "close", None)
            if close is not None:
                await close()


class GeminiSTT:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout: float = 30.0,
        client: Any | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("GEMINI_API_KEY is required for the gemini STT provider")
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self.model = model
        self._timeout = timeout

    async def transcribe(
        self, audio: bytes, mime: str = "audio/mpeg", language: str = "es-MX"
    ) -> TranscriptionResult:
        from google.genai import types

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model,
                    contents=[
                        types.Part.from_bytes(data=audio, mime_type=mime),
                        f"Transcribe este audio en {language}. Devuelve solo la transcripción.",
                    ],
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderUnavailableError("gemini STT timed out") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"gemini STT request failed: {exc!r}") from exc
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise ProviderResponseError("gemini STT returned an empty transcription")
        return TranscriptionResult(text=text, provider=self.name, language=language)


class FasterWhisperSTT:
    name = "faster_whisper"

    def __init__(self, model_size: str = "small") -> None:
        self._model_size = model_size
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        return self._model

    async def transcribe(
        self, audio: bytes, mime: str = "audio/mpeg", language: str = "es-MX"
    ) -> TranscriptionResult:
        def run() -> str:
            model = self._load()
            segments, _ = model.transcribe(io.BytesIO(audio), language=language[:2])
            return " ".join(segment.text.strip() for segment in segments).strip()

        try:
            text = await asyncio.to_thread(run)
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ProviderUnavailableError("faster-whisper is not installed") from exc
        except Exception as exc:  # pragma: no cover - model/runtime failure
            raise ProviderUnavailableError(f"faster-whisper failed: {exc!r}") from exc
        if not text:
            raise ProviderResponseError("faster-whisper returned an empty transcription")
        return TranscriptionResult(text=text, provider=self.name, language=language)


class NullSTT:
    name = "none"

    async def transcribe(
        self, audio: bytes, mime: str = "audio/mpeg", language: str = "es-MX"
    ) -> TranscriptionResult:
        raise ProviderUnavailableError("no STT provider is configured")


class FallbackSTT:
    def __init__(self, primary: STTProvider, fallback: STTProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def name(self) -> str:
        return f"{self._primary.name}->{self._fallback.name}"

    async def transcribe(
        self, audio: bytes, mime: str = "audio/mpeg", language: str = "es-MX"
    ) -> TranscriptionResult:
        try:
            return await self._primary.transcribe(audio, mime, language)
        except ProviderError:
            return await self._fallback.transcribe(audio, mime, language)
