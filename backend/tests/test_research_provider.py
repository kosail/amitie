import asyncio
import unittest

from config import Settings
from providers.base import ProviderResponseError, ProviderUnavailableError
from providers.registry import build_research
from providers.research import (
    COST_KEYS,
    FallbackResearch,
    GeminiGroundingResearch,
    ResearchSnapshot,
    StaticPriceTableResearch,
)


class _FailingProvider:
    name = "failing"

    async def research(self, query, hints=None):
        raise ProviderUnavailableError("boom")


class _WorkingProvider:
    name = "working"

    async def research(self, query, hints=None):
        return ResearchSnapshot(source="working", payload={key: 1.0 for key in COST_KEYS})


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


class StaticTableTest(unittest.TestCase):
    def test_known_destination(self) -> None:
        snapshot = asyncio.run(StaticPriceTableResearch().research("Viaje a Japón"))
        self.assertEqual(snapshot.source, "static_table")
        self.assertEqual(snapshot.payload["flight_roundtrip_mxn"], 28000.0)

    def test_unknown_destination_default(self) -> None:
        snapshot = asyncio.run(StaticPriceTableResearch().research("algo raro"))
        self.assertEqual(snapshot.payload["flight_roundtrip_mxn"], 12000.0)


class FallbackTest(unittest.TestCase):
    def test_falls_back_on_provider_error(self) -> None:
        chain = FallbackResearch(_FailingProvider(), StaticPriceTableResearch())
        snapshot = asyncio.run(chain.research("Viaje a Japón"))
        self.assertEqual(snapshot.source, "static_table")
        self.assertIn("->", chain.name)

    def test_uses_primary_when_healthy(self) -> None:
        snapshot = asyncio.run(FallbackResearch(_WorkingProvider(), StaticPriceTableResearch()).research("x"))
        self.assertEqual(snapshot.source, "working")


class GeminiGroundingTest(unittest.TestCase):
    def test_parses_json(self) -> None:
        payload = '{"flight_roundtrip_mxn": 30000, "lodging_per_night_mxn": 1500, "food_per_day_mxn": 800, "transport_per_day_mxn": 300}'
        provider = GeminiGroundingResearch("", "gemini-2.5-flash", client=_FakeClient(payload))
        snapshot = asyncio.run(provider.research("Viaje a Japón"))
        self.assertEqual(snapshot.source, "gemini_grounding")
        self.assertEqual(snapshot.payload["flight_roundtrip_mxn"], 30000.0)

    def test_rejects_non_json(self) -> None:
        provider = GeminiGroundingResearch("", "gemini-2.5-flash", client=_FakeClient("no soy json"))
        with self.assertRaises(ProviderResponseError):
            asyncio.run(provider.research("Viaje a Japón"))


class RegistryTest(unittest.TestCase):
    def test_static_only(self) -> None:
        provider = build_research(
            Settings(research_provider="static_table", research_fallback="static_table")
        )
        self.assertEqual(provider.name, "static_table")

    def test_grounding_with_fallback(self) -> None:
        provider = build_research(
            Settings(
                research_provider="gemini_grounding",
                research_fallback="static_table",
                gemini_api_key="dummy",
            )
        )
        self.assertEqual(provider.name, "gemini_grounding->static_table")


if __name__ == "__main__":
    unittest.main()
