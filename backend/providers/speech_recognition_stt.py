"""Local STT via the `SpeechRecognition` library.

Transcribes audio **bytes** the frontend sends (no microphone capture, so
`pyaudio` is not used). The default engine is Google Web Speech
(`recognize_google`) — the *library* is local, the recognition call is online.

MP3 and other compressed inputs are converted to WAV first via `pydub` (which
needs the `ffmpeg` binary). Set `pr_switch`/`STT_PROVIDER` to select this
provider; under `PR_SWITCH` it is used as the local engine.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any, Callable

from .base import ProviderResponseError, ProviderUnavailableError
from .voice import TranscriptionResult

_WAV_MIMES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}


class SpeechRecognitionSTT:
    name = "speech_recognition"

    def __init__(
        self,
        *,
        engine: str = "google",
        language: str = "es-MX",
        sr_module: Any | None = None,
        converter: Callable[[bytes, str], bytes] | None = None,
    ) -> None:
        self._engine = engine
        self._language = language
        self._sr = sr_module
        self._converter = converter

    def _module(self) -> Any:
        if self._sr is not None:
            return self._sr
        try:
            import speech_recognition as sr
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ProviderUnavailableError("SpeechRecognition is not installed") from exc
        return sr

    def _default_converter(self, audio: bytes, mime: str) -> bytes:
        try:
            from pydub import AudioSegment
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ProviderUnavailableError(
                "pydub is not installed (required to convert non-WAV audio)"
            ) from exc
        try:
            segment = AudioSegment.from_file(io.BytesIO(audio))
            out = io.BytesIO()
            segment.export(out, format="wav")
            return out.getvalue()
        except Exception as exc:  # pragma: no cover - ffmpeg/format failure
            raise ProviderUnavailableError(
                f"audio conversion failed (ffmpeg required): {exc!r}"
            ) from exc

    def _wav_bytes(self, audio: bytes, mime: str) -> bytes:
        if mime in _WAV_MIMES:
            return audio
        converter = self._converter or self._default_converter
        return converter(audio, mime)

    def _recognize(self, recognizer: Any, data: Any, language: str) -> str:
        sr = self._module()
        try:
            if self._engine in ("google", "google_web_speech"):
                return recognizer.recognize_google(data, language=language)
            if self._engine == "sphinx":
                return recognizer.recognize_sphinx(data, language=language)
            if self._engine == "vosk":
                return recognizer.recognize_vosk(data)
            raise ProviderUnavailableError(f"unsupported recognition engine {self._engine!r}")
        except sr.UnknownValueError as exc:
            raise ProviderResponseError("speech could not be understood") from exc
        except sr.RequestError as exc:
            raise ProviderUnavailableError(f"speech recognition request failed: {exc}") from exc

    async def transcribe(
        self, audio: bytes, mime: str = "audio/mpeg", language: str = "es-MX"
    ) -> TranscriptionResult:
        lang = language or self._language

        def run() -> str:
            sr = self._module()
            wav = self._wav_bytes(audio, mime)
            recognizer = sr.Recognizer()
            with sr.AudioFile(io.BytesIO(wav)) as source:
                data = recognizer.record(source)
            return self._recognize(recognizer, data, lang)

        text = (await asyncio.to_thread(run) or "").strip()
        if not text:
            raise ProviderResponseError("speech recognition returned empty text")
        return TranscriptionResult(text=text, provider=self.name, language=lang)
