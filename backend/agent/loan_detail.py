"""Per-loan personalized A2UI detail surface.

When the user opens a specific loan, the backend lazily builds (once) a fully
personalized A2UI page for that user+loan, then re-hydrates it on later visits
with fresh data. The template stores `{{placeholders}}` / `/loan/*` bindings, so
no financial value is frozen into it (INV-022).

Personalization is deterministic first (INV-015): the audience directive from
`get_audience` decides the interface complexity (elderly / low-literacy /
accessibility => color + emoji, simple language; high financial activity =>
denser, technical). The LLM only lays the interface out; it never computes
figures. The user's stated purpose (unless private) is enriched with a topical
web search, and those costs are shown as external reference spending.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Mapping

import structlog

from mcp_servers.toolbox import Toolbox
from providers.base import ChatMessage, LLMProvider, ProviderError
from providers.research import ResearchProvider
from ui_contract.catalog import CATALOG
from ui_contract.normalize import normalize_components
from ui_contract.validator import validate_messages

logger = structlog.get_logger(__name__)

DOMAIN = "loan_detail"

_DETAIL_COMPONENTS = (
    "Column",
    "Row",
    "Card",
    "Text",
    "Heading",
    "Divider",
    "Badge",
    "Button",
    "ProgressBar",
    "List",
    "PlanTable",
    "LineChart",
    "ScenarioComparison",
    "LoanOffer",
)

DETAIL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "response_text": {"type": "string"},
        "components": {"type": "array", "items": {"type": "object"}},
        "data_model": {"type": "object"},
    },
    "required": ["response_text", "components"],
}


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "$0"


def _describe_allowed() -> str:
    lines = []
    for name in _DETAIL_COMPONENTS:
        spec = CATALOG.components.get(name)
        if spec is None:
            continue
        required = ", ".join(spec.required) if spec.required else "none"
        props = ", ".join(f"{prop}: {token}" for prop, token in spec.props.items()) or "none"
        lines.append(f"- {name} | required: {required} | props: {props}")
    return "\n".join(lines)


def _compact_history(history: Any) -> dict[str, Any]:
    if not isinstance(history, dict):
        return {}
    return {key: value for key, value in history.items() if key != "recentTransactions"}


def _research_payload(research: Any) -> dict[str, Any] | None:
    if research is None:
        return None
    items = getattr(research, "items", None)
    if not items:
        return None
    return {
        "topic": getattr(research, "topic", ""),
        "summary": getattr(research, "summary", ""),
        "source": getattr(research, "source", ""),
        "items": list(items),
    }


class LoanDetailService:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        toolbox: Toolbox,
        research: ResearchProvider | None = None,
        tracer: Any | None = None,
        deadline_seconds: float = 8.0,
        max_tokens: int = 1800,
    ) -> None:
        self._provider = provider
        self._toolbox = toolbox
        self._research = research
        self._tracer = tracer
        self._deadline_seconds = deadline_seconds
        self._max_tokens = max_tokens

    async def get_or_create(self, *, user_id: str, loan_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        loan_result = await self._toolbox.call("get_loan", {"user_id": user_id, "loan_id": loan_id})
        loan = loan_result.get("loan") if isinstance(loan_result, dict) else None
        if not isinstance(loan, Mapping):
            return {"status": "not_found"}

        existing = await self._toolbox.call(
            "find_surface", {"user_id": user_id, "domain": DOMAIN, "entity_id": loan_id}
        )
        surface_id = existing.get("surface_id") if isinstance(existing, dict) else None
        if surface_id:
            hydrated = await self._toolbox.call("hydrate_ui", {"surface_id": surface_id})
            if hydrated.get("status") == "ok":
                logger.info("loan_detail_reused", user_id=user_id, loan_id=loan_id)
                return {"status": "ok", "loan_id": loan_id, "source": "stored", **self._payload(hydrated)}

        generated = await self._generate(user_id=user_id, loan=loan)
        persisted = await self._toolbox.call(
            "persist_ui",
            {
                "user_id": user_id,
                "domain": DOMAIN,
                "catalog_id": CATALOG.catalog_id,
                "components": generated["components"],
                "data_model": generated.get("data_model") or {},
                "entity_id": loan_id,
            },
        )
        if persisted.get("status") != "ok":
            return {
                "status": "error",
                "message": "; ".join(persisted.get("issues", ["no se pudo generar la página"])),
            }
        hydrated = await self._toolbox.call("hydrate_ui", {"surface_id": persisted["surface_id"]})
        await self._trace(started, error=None)
        logger.info(
            "loan_detail_generated",
            user_id=user_id,
            loan_id=loan_id,
            surface_id=persisted.get("surface_id"),
        )
        return {"status": "ok", "loan_id": loan_id, "source": "generated", **self._payload(hydrated)}

    @staticmethod
    def _payload(hydrated: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "catalog_id": hydrated.get("catalog_id"),
            "surface_id": hydrated.get("surface_id"),
            "a2ui": hydrated.get("a2ui", []),
            "audio_ref": hydrated.get("audio_ref") or None,
        }

    async def _research_purpose(self, purpose: str | None, private: bool) -> Any:
        if private or not purpose or self._research is None:
            return None
        try:
            return await asyncio.wait_for(
                self._research.research_topic(purpose), timeout=self._deadline_seconds
            )
        except Exception as exc:  # grounding/failover exhausted; stay deterministic
            logger.info("loan_detail_research_unavailable", error=f"{type(exc).__name__}: {exc}")
            return None

    async def _generate(self, *, user_id: str, loan: Mapping[str, Any]) -> dict[str, Any]:
        audience_result = await self._toolbox.call("get_audience", {"user_id": user_id})
        audience = audience_result.get("audience") if isinstance(audience_result, dict) else None
        history_result = await self._toolbox.call("get_credit_history", {"user_id": user_id})
        history = history_result.get("creditHistory", {}) if isinstance(history_result, dict) else {}
        profile = history.get("profile") if isinstance(history, Mapping) else None
        purpose = str(loan.get("purpose") or "").strip() or None
        private = bool(loan.get("purposePrivate"))
        research = await self._research_purpose(purpose, private)
        research_payload = _research_payload(research)

        messages = [
            ChatMessage(role="system", content=self._system_prompt(audience, research_payload)),
            ChatMessage(
                role="user",
                content=(
                    "CRÉDITO DEL USUARIO (datos reales; NO los inventes):\n"
                    + json.dumps(dict(loan), ensure_ascii=False)
                    + "\n\nDatos financieros del usuario (JSON):\n"
                    + json.dumps(_compact_history(history), ensure_ascii=False)
                    + "\n\nAudiencia determinista (nivel y complejidad obligatoria):\n"
                    + json.dumps(audience, ensure_ascii=False)
                    + "\n\nPropósito declarado: "
                    + (purpose if purpose else "(no especificado)")
                    + (" (PRIVADO: no se hizo búsqueda; personaliza solo con sus datos)"
                       if private else "")
                    + "\n\nCostos de referencia (búsqueda web; pueden ser null):\n"
                    + json.dumps(research_payload, ensure_ascii=False)
                ),
            ),
        ]

        parsed: dict[str, Any] | None = None
        try:
            generated = await asyncio.wait_for(
                self._provider.generate(
                    messages, response_schema=DETAIL_SCHEMA, max_tokens=self._max_tokens
                ),
                timeout=self._deadline_seconds,
            )
            parsed = self._parse_json(generated.text)
            components = normalize_components(parsed.get("components"))
            validation = validate_messages(
                [
                    {"version": CATALOG.version, "createSurface": {"surfaceId": "pending", "catalogId": CATALOG.catalog_id}},
                    {"version": CATALOG.version, "updateComponents": {"surfaceId": "pending", "components": components}},
                ]
            )
            if not validation.ok:
                raise ValueError("; ".join(validation.issues))
            parsed["components"] = components
        except (ProviderError, asyncio.TimeoutError, TimeoutError, ValueError, KeyError) as exc:
            logger.info("loan_detail_fallback", error=f"{type(exc).__name__}: {exc}")
            return self._fallback(loan, audience, research_payload, profile)

        data_model = parsed.get("data_model")
        if not isinstance(data_model, dict):
            data_model = {}
        data_model.setdefault("loan", dict(loan))
        if research_payload is not None:
            data_model.setdefault("purposeResearch", research_payload)
        return {
            "response_text": str(parsed.get("response_text") or ""),
            "components": parsed["components"],
            "data_model": data_model,
        }

    def _system_prompt(self, audience: Mapping[str, Any] | None, research: dict[str, Any] | None) -> str:
        level = str((audience or {}).get("level") or "standard")
        directive = str((audience or {}).get("directive") or "")
        lines = [
            "Eres Luna, asesora de crédito en México (es-MX). Generas la página A2UI que el usuario "
            "verá al abrir uno de SUS créditos. Habla en femenino.",
            "",
            "REGLAS ESTRICTAS:",
            "- NUNCA calcules cifras. El crédito ya está calculado: úsalo tal cual desde `/loan`.",
            "- Para todo valor variable usa placeholders {{dot.path}} en textos y bindings "
            '{"path": "/..."} en props numéricas. Nada de números de dinero escritos a mano.',
            "- La página es de ESTE crédito, independiente de cualquier otro. Personalízala.",
            "- Responde ÚNICAMENTE con JSON: "
            '{"response_text": "...", "components": [ ...A2UI flat... ], "data_model": { ... }}.',
            "",
            "DATOS DISPONIBLES (data_model raíz): loan (amount, monthlyPayment, termMonths, cat, "
            "totalInterest, totalCost, schedule), schedule, profile, liabilities, totals, incomeStreams, "
            "subscriptions, cashFlow, purposeResearch (topic, summary, items[{emoji,label,typical_mxn,note}]).",
            "",
            "OBLIGATORIO: incluye LoanOffer con amount, apr, months, monthlyPayment, totalInterest, "
            "totalCost, cat y schedule enlazados a /loan (p. ej. {\"path\": \"/loan/amount\"}).",
            "Sugerencia de estructura: un Heading de bienvenida, una Card con LoanOffer, y una sección "
            "que explique en términos financieros para qué es el crédito.",
        ]
        if research:
            topic = research.get("topic") or "el propósito"
            lines += [
                f"PROPÓSITO CON BÚSQUEDA WEB: hay costos de referencia sobre '{topic}'. Incluye una "
                "sección (Card + Text) titulada con el tema, mostrando cada concepto con su emoji y costo "
                "estimado usando {{purposeResearch.items.N.emoji}}, {{purposeResearch.items.N.label}} y "
                "{{purposeResearch.items.N.typical_mxn}}. Aterriza el monto del crédito contra esos costos.",
            ]
        else:
            lines += [
                "SIN BÚSQUEDA: no incluyas costos externos ni inventes precios. Personaliza solo con los "
                "datos financieros del usuario (sus gastos por categoría, ingreso y deudas).",
            ]
        lines += [
            "",
            "ADAPTACIÓN DE AUDIENCIA (obligatoria): " + (directive or f"nivel {level}"),
        ]
        if level == "simple":
            lines += [
                "Usa MUCHO emoji (una idea por Tarjeta), frases muy cortas y lenguaje llano; sin tablas "
                "densas ni tecnicismos; números grandes. El color (tone) y los íconos son la guía.",
            ]
        elif level == "detailed":
            lines += [
                "Puedes ser técnico: incluye CAT, calendario (PlanTable), comparación de escenarios y, si "
                "aplica, una gráfica (LineChart) del saldo. Una gráfica basta.",
            ]
        else:
            lines += [
                "Equilibra claridad y detalle: resumen, calendario de pagos y una comparación; explica los "
                "términos clave en una línea.",
            ]
        lines += [
            "",
            "COMPONENTES PERMITIDOS:",
            _describe_allowed(),
            "ACCIONES PERMITIDAS: " + ", ".join(CATALOG.actions),
            "FORMA (v0.9, flat): cada componente es {\"id\": ..., \"component\": \"Text\", ...props}.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        import re

        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("model output was not a JSON object")
        if not isinstance(parsed.get("components"), list) or not parsed["components"]:
            raise ValueError("no components")
        return parsed

    def _fallback(
        self,
        loan: Mapping[str, Any],
        audience: Mapping[str, Any] | None,
        research: dict[str, Any] | None,
        profile: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        name = str((profile or {}).get("name") or "").strip().split(" ")[0]
        level = str((audience or {}).get("level") or "standard")
        amount = _money(loan.get("amount"))
        payment = _money(loan.get("monthlyPayment"))
        months = int(loan.get("termMonths") or 0)
        emoji = "🎉 " if level == "simple" else ""
        components: list[dict[str, Any]] = [
            {"id": "root", "component": "Column", "gap": 12, "children": ["h1", "intro", "offer"]},
            {
                "id": "h1",
                "component": "Heading",
                "level": 1,
                "text": f"{emoji}Tu crédito{', ' + name if name else ''}",
            },
            {
                "id": "intro",
                "component": "Text",
                "variant": "body",
                "text": (
                    f"Pediste {amount} a {months} meses. Tu pago mensual es {payment}. "
                    "Aquí está el detalle de tu crédito."
                ),
            },
            {
                "id": "offer",
                "component": "LoanOffer",
                "amount": {"path": "/loan/amount"},
                "apr": {"path": "/loan/apr"},
                "months": {"path": "/loan/termMonths"},
                "monthlyPayment": {"path": "/loan/monthlyPayment"},
                "totalInterest": {"path": "/loan/totalInterest"},
                "totalCost": {"path": "/loan/totalCost"},
                "cat": {"path": "/loan/cat"},
                "schedule": {"path": "/loan/schedule"},
            },
        ]
        purpose = str(loan.get("purpose") or "").strip()
        if research and research.get("items"):
            components.append(
                {
                    "id": "purpose_title",
                    "component": "Heading",
                    "level": 2,
                    "text": f"Para tu {research.get('topic') or 'plan'}",
                }
            )
            components[0]["children"].append("purpose_title")
            for index, item in enumerate(research["items"]):
                if index >= 4:
                    break
                component_id = f"purpose_{index}"
                components.append(
                    {
                        "id": component_id,
                        "component": "Text",
                        "variant": "body",
                        "text": (
                            "{{purposeResearch.items."
                            + str(index)
                            + ".emoji}} {{purposeResearch.items."
                            + str(index)
                            + ".label}}: ~{{purposeResearch.items."
                            + str(index)
                            + ".typical_mxn}} MXN"
                        ),
                    }
                )
                components[0]["children"].append(component_id)
            if research.get("summary"):
                components.append(
                    {"id": "purpose_summary", "component": "Text", "variant": "caption", "text": str(research["summary"])}
                )
                components[0]["children"].append("purpose_summary")
        elif purpose and not loan.get("purposePrivate"):
            components.append(
                {
                    "id": "purpose_note",
                    "component": "Text",
                    "variant": "caption",
                    "text": f"Este crédito es para: {purpose}.",
                }
            )
            components[0]["children"].append("purpose_note")

        data_model: dict[str, Any] = {"loan": dict(loan)}
        if research:
            data_model["purposeResearch"] = research
        return {
            "response_text": f"Aquí está el detalle de tu crédito de {amount}.",
            "components": components,
            "data_model": data_model,
        }

    async def _trace(self, started: float, *, error: str | None) -> None:
        if self._tracer is None:
            return
        from observability.context import current_trace_id
        from observability.tracing import TraceEvent, new_trace_id

        trace_id = current_trace_id() or new_trace_id()
        await self._tracer.record(
            trace_id,
            TraceEvent(
                kind="llm",
                name="loan_detail",
                provider=getattr(self._provider, "name", "gateway"),
                model=getattr(self._provider, "model", None),
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=error,
            ),
        )
