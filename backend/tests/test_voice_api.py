"""POST /debug/stt and POST /debug/tts: isolated voice I/O with provider forcing."""

import base64
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from config import Settings
from providers.base import LLMResult, Usage
from providers.voice import SynthesisResult, TranscriptionResult


class FakeLLM:
    name = "fake"
    model = "fake"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        return LLMResult(text="ok", tool_calls=(), usage=Usage(), provider="fake", model="fake")


class FakeTTS:
    def __init__(self, name):
        self.name = name

    async def synthesize(self, text, voice_id="", speed=1.0):
        return SynthesisResult(b"MP3:" + text.encode(), "audio/mpeg", voice_id or "v", self.name)


class FakeSTT:
    def __init__(self, name):
        self.name = name

    async def transcribe(self, audio, mime="audio/mpeg", language="es-MX"):
        return TranscriptionResult(f"{self.name}:{audio.decode(errors='ignore')}", self.name, language)


class VoiceApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        settings = Settings(
            database_path=str(Path(self._tmp.name) / "voice.sqlite3"),
            audio_cache_dir=str(Path(self._tmp.name) / "audio"),
        )
        self.app = create_app(
            provider=FakeLLM(),
            settings=settings,
            tts=FakeTTS("chain-tts"),
            stt=FakeSTT("chain-stt"),
            tts_options={"elevenlabs": FakeTTS("elevenlabs"), "edge_tts": FakeTTS("edge_tts")},
            stt_options={"gemini": FakeSTT("gemini"), "faster_whisper": FakeSTT("faster_whisper")},
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_stt_forces_provider(self) -> None:
        with TestClient(self.app) as client:
            audio = base64.b64encode(b"hola").decode()
            forced = client.post("/debug/stt", json={"audio_b64": audio, "provider": "gemini"})
            self.assertEqual(forced.status_code, 200)
            self.assertEqual(forced.json()["status"], "ok")
            self.assertEqual(forced.json()["provider"], "gemini")
            self.assertEqual(forced.json()["text"], "gemini:hola")

            chained = client.post("/debug/stt", json={"audio_b64": audio})
            self.assertEqual(chained.json()["provider"], "chain-stt")

    def test_stt_unknown_provider_errors(self) -> None:
        with TestClient(self.app) as client:
            audio = base64.b64encode(b"hola").decode()
            body = client.post("/debug/stt", json={"audio_b64": audio, "provider": "bogus"}).json()
            self.assertEqual(body["status"], "error")
            self.assertIn("bogus", body["message"])

    def test_tts_writes_ref_and_serves_bytes(self) -> None:
        with TestClient(self.app) as client:
            body = client.post(
                "/debug/tts", json={"text": "hola", "provider": "elevenlabs"}
            ).json()
            self.assertEqual(body["status"], "ok", body)
            self.assertEqual(body["provider"], "elevenlabs")
            self.assertTrue(body["audio_ref"].startswith("/api/audio/"))
            self.assertGreater(body["bytes"], 0)

            served = client.get(body["audio_ref"])
            self.assertEqual(served.status_code, 200)
            self.assertEqual(served.content, b"MP3:hola")
            self.assertEqual(served.headers["content-type"], "audio/mpeg")

            second = client.post(
                "/debug/tts", json={"text": "hola", "provider": "elevenlabs"}
            ).json()
            self.assertTrue(second["cached"])
            self.assertEqual(second["audio_id"], body["audio_id"])

    def test_tts_raw_streams_bytes(self) -> None:
        with TestClient(self.app) as client:
            response = client.post(
                "/debug/tts", params={"raw": "true"}, json={"text": "adios", "provider": "edge_tts"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"MP3:adios")
            self.assertEqual(response.headers["content-type"], "audio/mpeg")
            self.assertEqual(response.headers["x-tts-provider"], "edge_tts")


class DebugKillSwitchTest(unittest.TestCase):
    def test_debug_routes_absent_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                database_path=str(Path(tmp) / "off.sqlite3"),
                audio_cache_dir=str(Path(tmp) / "audio"),
                enable_debug_endpoints=False,
            )
            app = create_app(
                provider=FakeLLM(), settings=settings, tts=FakeTTS("t"), stt=FakeSTT("s")
            )
            with TestClient(app) as client:
                self.assertEqual(client.get("/debug/providers").status_code, 404)
                self.assertEqual(client.get("/debug/kill-test/x").status_code, 404)
                self.assertEqual(
                    client.post("/debug/stt", json={"audio_b64": "eA=="}).status_code, 404
                )
                # Product routes are unaffected.
                self.assertEqual(client.get("/healthz").status_code, 200)


if __name__ == "__main__":
    unittest.main()
