"""GET /debug/providers attributes provider health per dependency."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from config import Settings
from providers.base import LLMResult, ProviderUnavailableError, Usage
from providers.gateway import FallbackLLM
from providers.research import ResearchSnapshot
from providers.voice import SynthesisResult


class GoodLLM:
    name = "gemini"
    model = "gemini-2.5-flash"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        return LLMResult(text="pong", tool_calls=(), usage=Usage(), provider=self.name, model=self.model)


class BadLLM:
    name = "deepseek"
    model = "deepseek-flash"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        raise ProviderUnavailableError("no key")


class GoodResearch:
    name = "gemini_grounding->static_table"

    async def research(self, query, hints=None):
        return ResearchSnapshot(source="static_table", payload={"flight_roundtrip_mxn": 1.0})


class GoodTTS:
    name = "edge_tts"

    async def synthesize(self, text, voice_id="", speed=1.0):
        return SynthesisResult(b"audio", "audio/mpeg", "v", "edge_tts")


class GoodSTT:
    name = "gemini"


class ProviderDoctorTest(unittest.TestCase):
    def _app(self, provider):
        self._tmp = tempfile.TemporaryDirectory()
        db_path = str(Path(self._tmp.name) / "doctor.sqlite3")
        return create_app(
            provider=provider,
            settings=Settings(database_path=db_path),
            research=GoodResearch(),
            tts=GoodTTS(),
            stt=GoodSTT(),
        )

    def test_reports_each_provider(self) -> None:
        app = self._app(FallbackLLM(GoodLLM(), BadLLM(), cooldown_seconds=0))
        try:
            with TestClient(app) as client:
                body = client.get("/debug/providers").json()
        finally:
            self._tmp.cleanup()

        by_name = {entry["name"]: entry for entry in body["providers"]}
        self.assertEqual(set(by_name), {"llm.primary", "llm.fallback", "research", "tts", "stt"})
        self.assertTrue(by_name["llm.primary"]["ok"])
        self.assertEqual(by_name["llm.primary"]["provider"], "gemini")
        self.assertFalse(by_name["llm.fallback"]["ok"])
        self.assertIn("no key", by_name["llm.fallback"]["error"])
        self.assertTrue(by_name["research"]["ok"])
        self.assertEqual(by_name["research"]["detail"], "static_table")
        self.assertTrue(by_name["tts"]["ok"])
        self.assertIsNone(by_name["stt"]["ok"])

    def test_single_provider_uses_llm_name(self) -> None:
        app = self._app(GoodLLM())
        try:
            with TestClient(app) as client:
                body = client.get("/debug/providers").json()
        finally:
            self._tmp.cleanup()
        names = [entry["name"] for entry in body["providers"]]
        self.assertIn("llm", names)


if __name__ == "__main__":
    unittest.main()
