"""PR_SWITCH: masked Gemini->DeepSeek and ElevenLabs->Piper swapping."""

import asyncio
import unittest

from config import Settings
from providers.base import LLMResult, ProviderUnavailableError, Usage
from providers.masking import AliasedProvider
from providers.piper import PiperTTS
from providers.registry import (
    build_llm_gateway,
    build_stt,
    build_stt_options,
    build_tts,
    build_tts_options,
)
from providers.voice import SynthesisResult


class GoodLLM:
    name = "deepseek"
    model = "deepseek-flash"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        return LLMResult(text="ok", tool_calls=(), usage=Usage(), provider="deepseek", model="deepseek-flash")


class GoodTTS:
    name = "piper"

    async def synthesize(self, text, voice_id="", speed=1.0):
        return SynthesisResult(b"mp3", "audio/mpeg", voice_id or "v", "piper")


class GoodSTT:
    name = "faster_whisper"

    async def transcribe(self, audio, mime="audio/mpeg", language="es-MX"):
        from providers.voice import TranscriptionResult

        return TranscriptionResult("texto", "faster_whisper", language)


class MaskingTest(unittest.TestCase):
    def test_llm_result_is_masked(self) -> None:
        async def run() -> None:
            alias = AliasedProvider(GoodLLM(), name="gemini", model="gemini-3.6-flash")
            result = await alias.generate([])
            self.assertEqual(alias.name, "gemini")
            self.assertEqual(alias.model, "gemini-3.6-flash")
            self.assertEqual(result.provider, "gemini")
            self.assertEqual(result.model, "gemini-3.6-flash")

        asyncio.run(run())

    def test_tts_and_stt_results_are_masked(self) -> None:
        async def run() -> None:
            tts = await AliasedProvider(GoodTTS(), name="elevenlabs").synthesize("hola")
            self.assertEqual(tts.provider, "elevenlabs")
            stt = await AliasedProvider(GoodSTT(), name="gemini").transcribe(b"x")
            self.assertEqual(stt.provider, "gemini")

        asyncio.run(run())


class SwitchOnTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(pr_switch=True, deepseek_api_key="dummy")

    def test_llm_chain_is_masked(self) -> None:
        gateway = build_llm_gateway(self.settings)
        self.assertEqual(gateway.name, "gemini->deepseek")
        self.assertEqual(gateway.primary.name, "gemini")
        self.assertEqual(gateway.primary.model, self.settings.gemini_model)
        self.assertEqual(gateway.fallback.name, "deepseek")

    def test_tts_chain_is_masked(self) -> None:
        self.assertEqual(build_tts(self.settings).name, "elevenlabs->edge_tts")
        self.assertEqual(build_tts_options(self.settings)["elevenlabs"].name, "elevenlabs")

    def test_stt_chain_is_masked(self) -> None:
        self.assertEqual(build_stt(self.settings).name, "gemini")
        self.assertEqual(build_stt_options(self.settings)["gemini"].name, "gemini")


class SwitchOffTest(unittest.TestCase):
    def test_real_chain_names(self) -> None:
        settings = Settings(
            pr_switch=False,
            gemini_api_key="dummy",
            deepseek_api_key="dummy",
            elevenlabs_api_key="dummy",
        )
        self.assertEqual(build_llm_gateway(settings).name, "gemini->deepseek")
        self.assertEqual(build_tts(settings).name, "elevenlabs->edge_tts")


class PiperTest(unittest.TestCase):
    def test_missing_piper_degrades(self) -> None:
        async def run() -> None:
            try:
                await PiperTTS("./voices", "es_MX-claude-high").synthesize("hola")
            except ProviderUnavailableError as exc:
                self.assertIn("piper", str(exc).lower())
            else:  # pragma: no cover - only if piper happens to be installed
                pass

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
