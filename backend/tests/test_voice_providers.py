import asyncio
import unittest

import httpx2

from config import Settings
from providers.base import ProviderResponseError, ProviderUnavailableError
from providers.registry import build_stt, build_tts
from providers.voice import (
    ElevenLabsTTS,
    FallbackSTT,
    FallbackTTS,
    GeminiSTT,
    NullSTT,
    NullTTS,
    SynthesisResult,
    TranscriptionResult,
)


class _FailingTTS:
    name = "failing"

    async def synthesize(self, text, voice_id="", speed=1.0):
        raise ProviderUnavailableError("boom")


class _WorkingTTS:
    name = "working"

    async def synthesize(self, text, voice_id="", speed=1.0):
        return SynthesisResult(b"audio", "audio/mpeg", voice_id or "v", self.name)


class _FailingSTT:
    name = "failing"

    async def transcribe(self, audio, mime="audio/mpeg", language="es-MX"):
        raise ProviderUnavailableError("boom")


class _WorkingSTT:
    name = "working"

    async def transcribe(self, audio, mime="audio/mpeg", language="es-MX"):
        return TranscriptionResult("hola", self.name, language)


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text):
        self._text = text

    async def generate_content(self, **kwargs):
        return _FakeResponse(self._text)


class _FakeAio:
    def __init__(self, text):
        self.models = _FakeModels(text)


class _FakeClient:
    def __init__(self, text):
        self.aio = _FakeAio(text)


class ElevenLabsTest(unittest.TestCase):
    def test_synthesizes_audio(self) -> None:
        def handler(request):
            return httpx2.Response(200, content=b"MP3BYTES", headers={"content-type": "audio/mpeg"})

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        provider = ElevenLabsTTS("key", default_voice_id="voice1", client=client)
        result = asyncio.run(provider.synthesize("hola"))
        self.assertEqual(result.audio, b"MP3BYTES")
        self.assertEqual(result.provider, "elevenlabs")
        asyncio.run(client.aclose())

    def test_rate_limit_is_unavailable(self) -> None:
        def handler(request):
            return httpx2.Response(429)

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        provider = ElevenLabsTTS("key", default_voice_id="voice1", client=client)
        with self.assertRaises(ProviderUnavailableError):
            asyncio.run(provider.synthesize("hola"))
        asyncio.run(client.aclose())

    def test_client_error_is_response_error(self) -> None:
        def handler(request):
            return httpx2.Response(400)

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        provider = ElevenLabsTTS("key", default_voice_id="voice1", client=client)
        with self.assertRaises(ProviderResponseError):
            asyncio.run(provider.synthesize("hola"))
        asyncio.run(client.aclose())


class GeminiSTTTest(unittest.TestCase):
    def test_transcribes(self) -> None:
        provider = GeminiSTT("", "gemini-2.5-flash", client=_FakeClient("quiero ahorrar"))
        result = asyncio.run(provider.transcribe(b"abc"))
        self.assertEqual(result.text, "quiero ahorrar")
        self.assertEqual(result.provider, "gemini")

    def test_empty_transcription_rejected(self) -> None:
        provider = GeminiSTT("", "gemini-2.5-flash", client=_FakeClient("   "))
        with self.assertRaises(ProviderResponseError):
            asyncio.run(provider.transcribe(b"abc"))


class FallbackTest(unittest.TestCase):
    def test_tts_falls_back(self) -> None:
        chain = FallbackTTS(_FailingTTS(), _WorkingTTS())
        result = asyncio.run(chain.synthesize("hola", "v", 1.0))
        self.assertEqual(result.provider, "working")
        self.assertIn("->", chain.name)

    def test_stt_falls_back(self) -> None:
        chain = FallbackSTT(_FailingSTT(), _WorkingSTT())
        result = asyncio.run(chain.transcribe(b"abc"))
        self.assertEqual(result.provider, "working")


class NullTest(unittest.TestCase):
    def test_null_tts_raises(self) -> None:
        with self.assertRaises(ProviderUnavailableError):
            asyncio.run(NullTTS().synthesize("x"))

    def test_null_stt_raises(self) -> None:
        with self.assertRaises(ProviderUnavailableError):
            asyncio.run(NullSTT().transcribe(b"x"))


class RegistryTest(unittest.TestCase):
    def test_degrades_without_keys(self) -> None:
        settings = Settings()
        self.assertEqual(build_tts(settings).name, "edge_tts")
        self.assertEqual(build_stt(settings).name, "faster_whisper")

    def test_elevenlabs_chain_with_key(self) -> None:
        settings = Settings(elevenlabs_api_key="dummy", elevenlabs_voice_id="v")
        self.assertEqual(build_tts(settings).name, "elevenlabs->edge_tts")


if __name__ == "__main__":
    unittest.main()
