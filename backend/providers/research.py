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

    async def research_topic(
        self, query: str, hints: dict[str, Any] | None = None
    ) -> "TopicResearch": ...


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

    async def research_topic(
        self, query: str, hints: dict[str, Any] | None = None
    ) -> "TopicResearch":
        """Deterministic topical cost breakdown (no network, no LLM)."""
        return _static_topic(self.name, query, hints)


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

    @staticmethod
    def _topic_prompt(query: str, hints: dict[str, Any] | None) -> str:
        return (
            "Eres un asistente de investigación financiera para México. Usa la búsqueda de Google "
            "para encontrar costos promedio reales en MXN relacionados con lo que el usuario quiere "
            "financiar. Responde ÚNICAMENTE con JSON con esta forma exacta: "
            '{"topic": "categoría corta", "items": [{"label": "concepto", "emoji": "🙂", '
            '"typical_mxn": 0, "note": "detalle breve"}], "summary": "una o dos frases en español"} '
            "Incluye entre 3 y 5 conceptos relevantes (p. ej. estudio: colegiatura, libros, transporte; "
            "viaje: vuelos, hospedaje, comidas, transporte; vida diaria: ropa, despensa, servicios). "
            f"Tema: {query}. Detalles: {json.dumps(hints or {}, ensure_ascii=False)}."
        )

    async def research_topic(
        self, query: str, hints: dict[str, Any] | None = None
    ) -> "TopicResearch":
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model,
                    contents=self._topic_prompt(query, hints),
                    config=self._config(),
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderUnavailableError(f"topic grounding timed out after {self._timeout}s") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"topic grounding request failed: {exc!r}") from exc

        text = getattr(response, "text", None) or ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError("topic grounding returned non-JSON output") from exc
        if not isinstance(parsed, dict):
            raise ProviderResponseError("topic grounding output was not an object")
        items = _coerce_topic_items(parsed.get("items"))
        if not items:
            raise ProviderResponseError("topic grounding returned no usable items")
        return TopicResearch(
            source=self.name,
            topic=str(parsed.get("topic") or query).strip() or str(query),
            items=items,
            summary=str(parsed.get("summary") or "").strip(),
        )


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

    async def research_topic(
        self, query: str, hints: dict[str, Any] | None = None
    ) -> "TopicResearch":
        try:
            return await self._primary.research_topic(query, hints)
        except ProviderError:
            return await self._fallback.research_topic(query, hints)


@dataclass(frozen=True)
class TopicResearch:
    """A topical cost breakdown used to personalize a loan's purpose."""

    source: str
    topic: str
    items: list[dict[str, Any]]
    summary: str


# (keywords, topic label, items). Deterministic fallback so the loan detail still
# has real-ish figures when grounding is unavailable (offline / PR_SWITCH).
_TOPIC_TABLE: tuple[tuple[tuple[str, ...], str, list[dict[str, Any]]], ...] = (
    (
        ("estudio", "escuela", "universidad", "maestria", "maestría", "curso", "educacion", "educación", "colegiatura", "carrera"),
        "estudios",
        [
            {"label": "Colegiatura (semestre)", "emoji": "🎓", "typical_mxn": 35000, "note": "universidad privada"},
            {"label": "Libros y útiles", "emoji": "📚", "typical_mxn": 4000, "note": "por semestre"},
            {"label": "Transporte", "emoji": "🚌", "typical_mxn": 1500, "note": "mensual"},
            {"label": "Equipo / laptop", "emoji": "💻", "typical_mxn": 12000, "note": "una vez"},
        ],
    ),
    (
        ("viaje", "viajar", "vacacion", "vacación", "playa", "vuelo", "turismo", "luna de miel"),
        "viaje",
        [
            {"label": "Vuelo redondo", "emoji": "✈️", "typical_mxn": 9000, "note": "nacional"},
            {"label": "Hospedaje por noche", "emoji": "🏨", "typical_mxn": 1500, "note": "por noche"},
            {"label": "Comidas por día", "emoji": "🍽️", "typical_mxn": 600, "note": "por día"},
            {"label": "Transporte local", "emoji": "🚕", "typical_mxn": 250, "note": "por día"},
        ],
    ),
    (
        ("vida diaria", "diario", "ropa", "despensa", "gastos", "hogar", "servicios", "casa"),
        "vida diaria",
        [
            {"label": "Despensa", "emoji": "🛒", "typical_mxn": 4500, "note": "mensual"},
            {"label": "Ropa y calzado", "emoji": "👕", "typical_mxn": 1500, "note": "mensual"},
            {"label": "Servicios (luz, agua, internet)", "emoji": "💡", "typical_mxn": 1800, "note": "mensual"},
            {"label": "Renta / hipoteca", "emoji": "🏠", "typical_mxn": 8000, "note": "mensual"},
        ],
    ),
    (
        ("negocio", "emprendimiento", "tienda", "inventario", "empresa", "pyme"),
        "negocio",
        [
            {"label": "Inventario inicial", "emoji": "📦", "typical_mxn": 25000, "note": "una vez"},
            {"label": "Renta de local", "emoji": "🏪", "typical_mxn": 12000, "note": "mensual"},
            {"label": "Equipo y herramientas", "emoji": "🧰", "typical_mxn": 15000, "note": "una vez"},
        ],
    ),
    (
        ("auto", "carro", "moto", "vehiculo", "vehículo", "camioneta"),
        "auto",
        [
            {"label": "Enganche", "emoji": "🚗", "typical_mxn": 40000, "note": "20% del valor"},
            {"label": "Seguro anual", "emoji": "🛡️", "typical_mxn": 9000, "note": "anual"},
            {"label": "Mantenimiento", "emoji": "🔧", "typical_mxn": 3500, "note": "por servicio"},
        ],
    ),
    (
        ("salud", "medico", "médico", "medicina", "hospital", "dental", "enfermedad", "tratamiento"),
        "salud",
        [
            {"label": "Consulta / tratamiento", "emoji": "🩺", "typical_mxn": 3500, "note": "por consulta"},
            {"label": "Medicamentos", "emoji": "💊", "typical_mxn": 2000, "note": "por tratamiento"},
            {"label": "Estudios de laboratorio", "emoji": "🧪", "typical_mxn": 2500, "note": "por estudio"},
        ],
    ),
    (
        ("deuda", "tarjeta", "consolidar", "pagar", "adeudo"),
        "deudas",
        [
            {"label": "Pago de tarjeta", "emoji": "💳", "typical_mxn": 8000, "note": "saldo actual"},
            {"label": "Préstamo personal", "emoji": "🏦", "typical_mxn": 15000, "note": "saldo actual"},
        ],
    ),
    (
        ("boda", "evento", "fiesta", "xv", "cumpleaños"),
        "evento",
        [
            {"label": "Banquete por persona", "emoji": "🍽️", "typical_mxn": 1200, "note": "por persona"},
            {"label": "Vestimenta", "emoji": "👗", "typical_mxn": 8000, "note": "una vez"},
            {"label": "Salón y música", "emoji": "🎉", "typical_mxn": 30000, "note": "una vez"},
        ],
    ),
)

_DEFAULT_TOPIC_ITEMS: list[dict[str, Any]] = [
    {"label": "Gasto principal", "emoji": "💡", "typical_mxn": 5000, "note": "estimado"},
    {"label": "Gastos relacionados", "emoji": "🧾", "typical_mxn": 2000, "note": "estimado"},
]


def _coerce_topic_items(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        if not label:
            continue
        try:
            amount = round(float(entry.get("typical_mxn") or entry.get("typicalMxn") or 0.0), 2)
        except (TypeError, ValueError):
            amount = 0.0
        items.append(
            {
                "label": label,
                "emoji": str(entry.get("emoji") or "💡").strip() or "💡",
                "typical_mxn": amount,
                "note": str(entry.get("note") or "").strip(),
            }
        )
    return items[:6]


def _static_topic(source: str, query: str, hints: dict[str, Any] | None = None) -> TopicResearch:
    text = f"{query} {json.dumps(hints or {}, ensure_ascii=False)}".lower()
    for keywords, topic, items in _TOPIC_TABLE:
        if any(keyword in text for keyword in keywords):
            return TopicResearch(source=source, topic=topic, items=[dict(item) for item in items], summary="")
    return TopicResearch(
        source=source,
        topic=str(query).strip() or "gastos",
        items=[dict(item) for item in _DEFAULT_TOPIC_ITEMS],
        summary="",
    )
