"""Research provider chain (INV-012, INV-013).

Web research is a provider like any other: Gemini with Google Search grounding
is primary, a deterministic price table is the fallback. Switching either is an
`.env` change. The provider returns a cost snapshot; the engine turns it into an
estimate (INV-015: the LLM never does the arithmetic).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .base import ProviderError, ProviderResponseError, ProviderUnavailableError

COST_KEYS = (
    "flight_roundtrip_mxn",
    "lodging_per_night_mxn",
    "food_per_day_mxn",
    "transport_per_day_mxn",
)

_DEFAULT_TABLE: dict[str, float] = {
    "flight_roundtrip_mxn": 12000.0,
    "lodging_per_night_mxn": 1200.0,
    "food_per_day_mxn": 500.0,
    "transport_per_day_mxn": 200.0,
}

_KNOWN_DESTINATIONS: tuple[tuple[tuple[str, ...], dict[str, float]], ...] = (
    (
        ("japon", "japón", "japan", "tokio", "tokyo", "kioto", "kyoto"),
        {
            "flight_roundtrip_mxn": 28000.0,
            "lodging_per_night_mxn": 1400.0,
            "food_per_day_mxn": 700.0,
            "transport_per_day_mxn": 250.0,
        },
    ),
    (
        ("europa", "europe", "espana", "españa", "paris", "roma"),
        {
            "flight_roundtrip_mxn": 22000.0,
            "lodging_per_night_mxn": 1800.0,
            "food_per_day_mxn": 900.0,
            "transport_per_day_mxn": 350.0,
        },
    ),
    (
        ("playa", "cancun", "cancún", "beach", "caribe"),
        {
            "flight_roundtrip_mxn": 9000.0,
            "lodging_per_night_mxn": 2500.0,
            "food_per_day_mxn": 600.0,
            "transport_per_day_mxn": 200.0,
        },
    ),
)


@dataclass(frozen=True)
class ResearchSnapshot:
    source: str
    payload: dict[str, float]


@runtime_checkable
class ResearchProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def research(self, query: str, hints: dict[str, Any] | None = None) -> ResearchSnapshot: ...


def _coerce(payload: dict[str, Any]) -> dict[str, float]:
    costs: dict[str, float] = {}
    for key in COST_KEYS:
        value = payload.get(key, _DEFAULT_TABLE[key])
        try:
            costs[key] = round(float(value), 2)
        except (TypeError, ValueError):
            costs[key] = _DEFAULT_TABLE[key]
    return costs


class StaticPriceTableResearch:
    """Deterministic fallback (REQ-BAG-05). No network, no LLM."""

    name = "static_table"

    async def research(self, query: str, hints: dict[str, Any] | None = None) -> ResearchSnapshot:
        text = f"{query} {json.dumps(hints or {})}".lower()
        table = _DEFAULT_TABLE
        for keywords, candidate in _KNOWN_DESTINATIONS:
            if any(keyword in text for keyword in keywords):
                table = candidate
                break
        return ResearchSnapshot(source=self.name, payload=dict(table))


class GeminiGroundingResearch:
    """Primary research provider: Gemini with Google Search grounding (REQ-BAG-03)."""

    name = "gemini_grounding"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 8.0,
        client: Any | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("GEMINI_API_KEY is required for the gemini_grounding provider")
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self.model = model
        self._timeout = timeout_seconds

    def _config(self) -> Any:
        from google.genai import types

        return types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            response_mime_type="application/json",
        )

    @staticmethod
    def _prompt(query: str, hints: dict[str, Any] | None) -> str:
        return (
            "Eres un asistente de investigación de precios para un plan de ahorro en México. "
            "Usa la búsqueda de Google para encontrar costos promedio reales en MXN y responde "
            "ÚNICAMENTE con JSON usando exactamente estas claves numéricas: "
            "flight_roundtrip_mxn, lodging_per_night_mxn, food_per_day_mxn, transport_per_day_mxn. "
            f"Objetivo: {query}. Detalles: {json.dumps(hints or {}, ensure_ascii=False)}."
        )

    async def research(self, query: str, hints: dict[str, Any] | None = None) -> ResearchSnapshot:
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model,
                    contents=self._prompt(query, hints),
                    config=self._config(),
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderUnavailableError(f"grounding timed out after {self._timeout}s") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"grounding request failed: {exc!r}") from exc

        text = getattr(response, "text", None) or ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError("grounding returned non-JSON output") from exc
        if not isinstance(parsed, dict):
            raise ProviderResponseError("grounding output was not an object")
        return ResearchSnapshot(source=self.name, payload=_coerce(parsed))


class FallbackResearch:
    """Try the primary provider, transparently fall back on any provider failure."""

    def __init__(self, primary: ResearchProvider, fallback: ResearchProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def name(self) -> str:
        return f"{self._primary.name}->{self._fallback.name}"

    async def research(self, query: str, hints: dict[str, Any] | None = None) -> ResearchSnapshot:
        try:
            return await self._primary.research(query, hints)
        except ProviderError:
            return await self._fallback.research(query, hints)
