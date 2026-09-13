"""Per-credit personalized A2UI detail surface (loans and liabilities).

When the user opens a specific credit — a loan they already took, or an active
liability (card / debt) — the backend lazily builds (once) an INFORMATIONAL A2UI
page for that user+entity, then re-hydrates it with fresh data on later visits.
The template stores `{{placeholders}}` / `/loan`|`/liability` bindings, so no
financial value is frozen into it (INV-022).

This page is NOT an offer: the credit is already granted/active. The generator
must never emit offer/accept semantics, and a deterministic guard strips any
`LoanOffer` component or `request_loan` action that slips through. For
liabilities the page DOES carry an `abonar` action (payment) that the client
routes to its native payment flow.

Personalization is deterministic first (INV-015): the audience directive decides
the interface complexity (elderly / low-literacy / accessibility => color +
emoji, simple language; higher financial activity => denser, technical). The LLM
only lays the interface out; it never computes figures. A loan's stated purpose
(unless private) is enriched with a topical web search; liabilities perform no
research.
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

LOAN_DOMAIN = "loan_detail"
LIABILITY_DOMAIN = "liability_detail"

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
    "LoanSummary",
    "LiabilitySummary",
)

_ENTITY = {
    "loan": {"domain": LOAN_DOMAIN, "id_key": "loan_id", "record_key": "loan", "summary": "LoanSummary"},
    "liability": {
        "domain": LIABILITY_DOMAIN,
        "id_key": "liability_id",
        "record_key": "liability",
        "summary": "LiabilitySummary",
    },
}

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


def _strip_offer_semantics(components: list[Any]) -> list[Any]:
    """Guarantee a taken credit is never presented as an offer.

    Removes every `LoanOffer` component (and references to it), and drops any
    `request_loan` action. Deterministic, so correctness never depends on the
    model obeying the prompt.
    """
    removed: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            continue
        component_id = component.get("id")
        action = component.get("action")
        action_name = (action.get("event") or {}).get("name") if isinstance(action, dict) else None
        # An offer card, or an action button whose only purpose was to accept:
        # both lose their meaning on a taken credit, so drop them entirely
        # (a Button without its action would itself fail validation).
        if (
            isinstance(component_id, str)
            and (component.get("component") == "LoanOffer" or action_name == "request_loan")
        ):
            removed.add(component_id)

    cleaned: list[Any] = []
    for component in components:
        if not isinstance(component, dict):
            cleaned.append(component)
            continue
        if component.get("id") in removed:
            continue
        copy = dict(component)
        children = copy.get("children")
        if isinstance(children, list):
            copy["children"] = [child for child in children if child not in removed]
        if copy.get("child") in removed:
            copy.pop("child", None)
        action = copy.get("action")
        if isinstance(action, dict):
            name = (action.get("event") or {}).get("name")
            if name == "request_loan":
                copy.pop("action", None)
        cleaned.append(copy)
    return cleaned


def _has_component(components: list[Any], component_type: str) -> bool:
    return any(
        isinstance(component, dict) and component.get("component") == component_type
        for component in components
    )


def _has_action(components: list[Any], action_name: str) -> bool:
    for component in components:
        if not isinstance(component, dict):
            continue
        action = component.get("action")
        if isinstance(action, dict) and (action.get("event") or {}).get("name") == action_name:
            return True
    return False


def _root_id(components: list[Any]) -> str | None:
    for component in components:
        if isinstance(component, dict) and isinstance(component.get("children"), list):
            return str(component.get("id"))
    return None


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

    async def get_or_create(self, *, user_id: str, entity: str, entity_id: str) -> dict[str, Any]:
        spec = _ENTITY.get(entity)
        if spec is None:
            return {"status": "error", "message": f"unknown entity {entity!r}"}
        started = time.perf_counter()

        found = await self._toolbox.call(
            f"get_{entity}", {"user_id": user_id, spec["id_key"]: entity_id}
        )
        record = found.get(spec["record_key"]) if isinstance(found, dict) else None
        if not isinstance(record, Mapping):
            return {"status": "not_found"}

        existing = await self._toolbox.call(
            "find_surface",
            {"user_id": user_id, "domain": spec["domain"], "entity_id": entity_id},
        )
        surface_id = existing.get("surface_id") if isinstance(existing, dict) else None
        if surface_id:
            hydrated = await self._toolbox.call("hydrate_ui", {"surface_id": surface_id})
            if hydrated.get("status") == "ok":
                logger.info("credit_detail_reused", user_id=user_id, entity=entity, entity_id=entity_id)
                return {
                    "status": "ok",
                    "entity": entity,
                    "entity_id": entity_id,
                    "source": "stored",
                    **self._payload(hydrated),
                }

        generated = await self._generate(
            user_id=user_id, entity=entity, record=record, spec=spec
        )
        persisted = await self._toolbox.call(
            "persist_ui",
            {
                "user_id": user_id,
                "domain": spec["domain"],
                "catalog_id": CATALOG.catalog_id,
                "components": generated["components"],
                "data_model": generated.get("data_model") or {},
                "entity_id": entity_id,
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
            "credit_detail_generated",
            user_id=user_id,
            entity=entity,
            entity_id=entity_id,
            surface_id=persisted.get("surface_id"),
        )
        return {
            "status": "ok",
            "entity": entity,
            "entity_id": entity_id,
            "source": "generated",
            **self._payload(hydrated),
        }

    @staticmethod
    def _payload(hydrated: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "catalog_id": hydrated.get("catalog_id"),
            "surface_id": hydrated.get("surface_id"),
            "a2ui": hydrated.get("a2ui", []),
            # Detail pages never carry audio (no TTS here).
            "audio_ref": None,
        }

    async def _research_purpose(self, record: Mapping[str, Any]) -> Any:
        purpose = str(record.get("purpose") or "").strip()
        private = bool(record.get("purposePrivate"))
        if private or not purpose or self._research is None:
            return None
        try:
            return await asyncio.wait_for(
                self._research.research_topic(purpose), timeout=self._deadline_seconds
            )
        except Exception as exc:  # grounding/failover exhausted; stay deterministic
            logger.info("credit_detail_research_unavailable", error=f"{type(exc).__name__}: {exc}")
            return None

    async def _generate(
        self, *, user_id: str, entity: str, record: Mapping[str, Any], spec: Mapping[str, Any]
    ) -> dict[str, Any]:
        audience_result = await self._toolbox.call("get_audience", {"user_id": user_id})
        audience = audience_result.get("audience") if isinstance(audience_result, dict) else None
        history_result = await self._toolbox.call("get_credit_history", {"user_id": user_id})
        history = history_result.get("creditHistory", {}) if isinstance(history_result, dict) else {}
        profile = history.get("profile") if isinstance(history, Mapping) else None
        research = await self._research_purpose(record) if entity == "loan" else None
        research_payload = _research_payload(research)

        messages = [
            ChatMessage(role="system", content=self._system_prompt(entity, spec, audience, research_payload)),
            ChatMessage(
                role="user",
                content=(
                    f"{entity.upper()} DEL USUARIO (datos reales; NO los inventes):\n"
                    + json.dumps(dict(record), ensure_ascii=False)
                    + "\n\nDatos financieros del usuario (JSON):\n"
                    + json.dumps(_compact_history(history), ensure_ascii=False)
                    + "\n\nAudiencia determinista (nivel y complejidad obligatoria):\n"
                    + json.dumps(audience, ensure_ascii=False)
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
            parsed["components"] = normalize_components(parsed.get("components"))
        except (ProviderError, asyncio.TimeoutError, TimeoutError, ValueError, KeyError) as exc:
            logger.info("credit_detail_fallback", entity=entity, error=f"{type(exc).__name__}: {exc}")
            return self._fallback(entity, spec, record, audience, research_payload, profile)

        components = _strip_offer_semantics(parsed["components"])
        if not _has_component(components, str(spec["summary"])):
            components = self._fallback(
                entity, spec, record, audience, research_payload, profile
            )["components"]
        if entity == "liability" and not _has_action(components, "abonar"):
            components = _ensure_abonar(components)

        validation = validate_messages(
            [
                {"version": CATALOG.version, "createSurface": {"surfaceId": "pending", "catalogId": CATALOG.catalog_id}},
                {"version": CATALOG.version, "updateComponents": {"surfaceId": "pending", "components": components}},
            ]
        )
        if not validation.ok:
            logger.info("credit_detail_invalid", entity=entity, issues=list(validation.issues))
            return self._fallback(entity, spec, record, audience, research_payload, profile)

        data_model = parsed.get("data_model")
        if not isinstance(data_model, dict):
            data_model = {}
        data_model.setdefault(spec["record_key"], dict(record))
        if research_payload is not None:
            data_model.setdefault("purposeResearch", research_payload)
        return {
            "response_text": str(parsed.get("response_text") or ""),
            "components": components,
            "data_model": data_model,
        }

    def _system_prompt(
        self,
        entity: str,
        spec: Mapping[str, Any],
        audience: Mapping[str, Any] | None,
        research: dict[str, Any] | None,
    ) -> str:
        level = str((audience or {}).get("level") or "standard")
        directive = str((audience or {}).get("directive") or "")
        is_loan = entity == "loan"
        summary = spec["summary"]
        record_key = spec["record_key"]
        lines = [
            "Eres Luna, asesora financiera en México (es-MX). Generas la página A2UI INFORMATIVA que "
            f"el usuario verá al abrir {'uno de SUS créditos ya otorgados' if is_loan else 'una de sus deudas activas'}.",
            "",
            "REGLAS ESTRICTAS:",
            "- El crédito YA fue otorgado y está ACTIVO. Esto NO es una oferta: PROHIBIDO usar el "
            "componente LoanOffer, PROHIBIDO la acción request_loan, y PROHIBIDO pedir aceptar o declinar.",
            "- NUNCA calcules cifras. Los valores ya están calculados: úsalos desde el contexto.",
            "- Para todo valor variable usa placeholders {{dot.path}} en textos y bindings "
            '{"path": "/..."} en props numéricas. Nunca escribas montos a mano.',
            "- La página es de ESTE crédito, independiente de cualquier otro. Personalízala.",
            "- Responde ÚNICAMENTE con JSON: "
            '{"response_text": "...", "components": [ ...A2UI flat... ], "data_model": { ... }}.',
            "",
            f"OBLIGATORIO: incluye {summary} enlazado a /{record_key} "
            f"(p. ej. {{\"path\": \"/{record_key}/amount\"}}). Es la tarjeta de resumen del crédito.",
            "",
            "SECCIONES OBLIGATORIAS (adapta el lenguaje a la audiencia):",
            "1) Resumen del crédito (la tarjeta " + summary + ").",
            "2) Cómo se reparte tu pago: capital vs intereses en el tiempo "
            "(usa el calendario /schedule o /payoff/schedule; puede ser PlanTable o LineChart).",
            "3) Tu situación hoy: riesgos e insights según el comportamiento financiero actual "
            "(usa /risk, /warnings, /cashFlow, /totals).",
        ]
        if is_loan and research:
            topic = research.get("topic") or "el propósito"
            lines += [
                "4) PROPÓSITO CON BÚSQUEDA WEB: hay costos de referencia sobre '" + str(topic) + "'. "
                "Incluye una sección (Card + Text) que muestre cada concepto con su emoji y costo estimado "
                "usando {{purposeResearch.items.N.emoji}}, {{purposeResearch.items.N.label}} y "
                "{{purposeResearch.items.N.typical_mxn}}, y aterriza el monto contra esos costos.",
            ]
        elif is_loan:
            lines += [
                "4) SIN BÚSQUEDA: no incluyas costos externos ni inventes precios. Personaliza solo con "
                "los datos financieros del usuario.",
            ]
        if not is_loan:
            lines += [
                "4) ABONAR: incluye un Button (destacado) con action "
                '{"event": {"name": "abonar", "context": {}}} para que el usuario abone a esta deuda. '
                "El monto lo elige la app; no lo pidas en el texto.",
            ]
        lines += [
            "",
            "ESTRUCTURA SEGÚN EL PERFIL (obligatoria):",
        ]
        if level == "simple":
            lines += [
                "- simple: usa MUCHO emoji (una idea por Card), frases muy cortas y lenguaje llano; "
                "NO uses PlanTable ni LineChart; usa ProgressBar y dos números grandes (capital vs intereses).",
            ]
        elif level == "detailed":
            lines += [
                "- detailed: puedes ser técnico; incluye AMBOS PlanTable y LineChart (saldo), y muestra "
                "las métricas de riesgo (DTI, colchón, APR vs tu deuda más cara, estabilidad de ingreso).",
            ]
        else:
            lines += [
                "- standard: equilibra claridad y detalle; incluye UNA vista de reparto (PlanTable O "
                "LineChart) y un resumen breve de riesgos.",
            ]
        lines += [
            "",
            "ADAPTACIÓN DE AUDIENCIA (obligatoria): " + (directive or f"nivel {level}"),
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
        entity: str,
        spec: Mapping[str, Any],
        record: Mapping[str, Any],
        audience: Mapping[str, Any] | None,
        research: dict[str, Any] | None,
        profile: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        level = str((audience or {}).get("level") or "standard")
        name = str((profile or {}).get("name") or "").strip().split(" ")[0]
        summary = spec["summary"]
        record_key = spec["record_key"]
        emoji = "✨ " if level == "simple" else ""
        components: list[dict[str, Any]] = [
            {"id": "root", "component": "Column", "gap": 12, "children": ["h1", "summary"]},
            {
                "id": "h1",
                "component": "Heading",
                "level": 1,
                "text": f"{emoji}Tu crédito{', ' + name if name else ''}"
                if entity == "loan"
                else f"{emoji}Tu deuda{', ' + name if name else ''}",
            },
        ]
        if entity == "loan":
            components.append(
                {
                    "id": "summary",
                    "component": "LoanSummary",
                    "amount": {"path": "/loan/amount"},
                    "apr": {"path": "/loan/apr"},
                    "months": {"path": "/loan/termMonths"},
                    "monthlyPayment": {"path": "/loan/monthlyPayment"},
                    "totalInterest": {"path": "/loan/totalInterest"},
                    "totalCost": {"path": "/loan/totalCost"},
                    "cat": {"path": "/loan/cat"},
                    "status": {"path": "/loan/status"},
                    "remainingBalance": {"path": "/loan/amount"},
                    "progress": {"path": "/progressPercent"},
                    "tone": "neutral",
                }
            )
        else:
            components.append(
                {
                    "id": "summary",
                    "component": "LiabilitySummary",
                    "creditor": {"path": "/liability/creditor"},
                    "kind": {"path": "/liability/kind"},
                    "principal": {"path": "/liability/principal"},
                    "balance": {"path": "/liability/balance"},
                    "apr": {"path": "/liability/apr"},
                    "minPayment": {"path": "/liability/minPayment"},
                    "dueDay": {"path": "/liability/dueDay"},
                    "progress": {"path": "/progressPercent"},
                    "tone": "neutral",
                }
            )

        # Distribution: charts/tables only for non-simple profiles.
        if level != "simple":
            points_path = "/schedule" if entity == "loan" else "/payoff/schedule"
            if level == "detailed":
                components += [
                    {"id": "dist_title", "component": "Heading", "level": 2, "text": "Cómo se reparte tu pago"},
                    {
                        "id": "dist_chart",
                        "component": "LineChart",
                        "points": {"path": points_path},
                        "title": "Saldo a lo largo del tiempo",
                        "yLabel": "MXN",
                    },
                    {"id": "dist_table", "component": "PlanTable", "months": {"path": points_path}},
                ]
                components[0]["children"] += ["dist_title", "dist_chart", "dist_table"]
            else:
                components += [
                    {"id": "dist_title", "component": "Heading", "level": 2, "text": "Cómo se reparte tu pago"},
                    {"id": "dist_table", "component": "PlanTable", "months": {"path": points_path}},
                ]
                components[0]["children"] += ["dist_title", "dist_table"]
        else:
            components += [
                {
                    "id": "progress",
                    "component": "ProgressBar",
                    "value": {"path": "/progressPercent"},
                    "max": 100,
                    "label": "Pagado",
                },
            ]
            components[0]["children"].append("progress")

        # Risk / situation.
        components.append(
            {"id": "risk_title", "component": "Heading", "level": 2, "text": "Tu situación hoy"}
        )
        components[0]["children"].append("risk_title")
        if entity == "loan":
            components.append(
                {
                    "id": "risk_note",
                    "component": "Text",
                    "variant": "body",
                    "text": "Revisa tu capacidad de pago y tu colchón en la evaluación de abajo.",
                }
            )
            components[0]["children"].append("risk_note")
        else:
            components.append(
                {
                    "id": "risk_note",
                    "component": "Text",
                    "variant": "body",
                    "text": "Tu pago mínimo representa {{risk.dti.existing}} de tu ingreso mensual.",
                }
            )
            components[0]["children"].append("risk_note")
            components.append(
                {
                    "id": "abonar",
                    "component": "Button",
                    "label": "Abonar a esta deuda",
                    "variant": "primary",
                    "action": {"event": {"name": "abonar", "context": {}}},
                }
            )
            components[0]["children"].append("abonar")

        # Purpose research (loans only).
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
            for index, _item in enumerate(research["items"][:4]):
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

        data_model: dict[str, Any] = {record_key: dict(record)}
        if research:
            data_model["purposeResearch"] = research
        return {
            "response_text": "Aquí está el detalle de tu crédito.",
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
                name="credit_detail",
                provider=getattr(self._provider, "name", "gateway"),
                model=getattr(self._provider, "model", None),
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=error,
            ),
        )


def _ensure_abonar(components: list[Any]) -> list[Any]:
    """Append a deterministic `abonar` button when the model omitted it."""
    root_id = _root_id(components)
    components = list(components)
    components.append(
        {
            "id": "abonar",
            "component": "Button",
            "label": "Abonar a esta deuda",
            "variant": "primary",
            "action": {"event": {"name": "abonar", "context": {}}},
        }
    )
    if root_id is not None:
        for component in components:
            if isinstance(component, dict) and str(component.get("id")) == root_id:
                children = component.get("children")
                if isinstance(children, list) and "abonar" not in children:
                    children.append("abonar")
    return components
