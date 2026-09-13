"""Voice-first loans & credits consult (single structured LLM call).

See `LOANS_CONSULT_GUIDE.md`. One model call returns
`{response_text, confidence, terminal_response}`; the terminal UI is persisted
(placeholders + loan association) only when confidence > 0.80, and the spoken
answer is always synthesized to mp3.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from mcp_servers.toolbox import Toolbox
from providers.base import ChatMessage, LLMProvider, ProviderError
from ui_contract.catalog import CATALOG
from ui_contract.normalize import normalize_components
from ui_contract.validator import validate_messages

from . import loans_fallback
from .bank_context import load_bank_context
import structlog

logger = structlog.get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.80


LOANS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "response_text": {"type": "string"},
        "confidence": {"type": "number"},
        "terminal_response": {
            "type": ["object", "null"],
            "properties": {
                "catalog_id": {"type": "string"},
                "components": {"type": "array", "items": {"type": "object"}},
                "data_model": {"type": "object"},
                "simulation": {"type": "object"},
            },
        },
    },
    "required": ["response_text", "confidence"],
}

GREETING = (
    "Hola, soy La Mesa, tu asesor de crédito. Cuéntame qué necesitas: "
    "por ejemplo, cuánto monto buscas y para qué lo usarías."
)

# Lo terminal component set the mobile catalog implements for the loans consult.
_LOANS_COMPONENTS = (
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
    "ScenarioComparison",
    "PlanTable",
    "ForecastChart",
    "LineChart",
    "BreakAlert",
    "LoanOffer",
)


def _describe_allowed() -> str:
    lines = []
    for name in _LOANS_COMPONENTS:
        spec = CATALOG.components.get(name)
        if spec is None:
            continue
        required = ", ".join(spec.required) if spec.required else "none"
        props = ", ".join(f"{prop}: {token}" for prop, token in spec.props.items()) or "none"
        lines.append(f"- {name} | required: {required} | props: {props}")
    return "\n".join(lines)


def _compact_credit_history(history: Any) -> dict[str, Any]:
    """Drop raw transactions (latency) while keeping the aggregate picture."""
    if not isinstance(history, dict):
        return {}
    return {key: value for key, value in history.items() if key != "recentTransactions"}



def _parse_json(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("model output was not a JSON object")
    return parsed


def _extract_amount(text: str) -> float | None:
    """Best-effort deterministic amount from the user's message (digits, mil/k)."""
    if not text:
        return None
    best: float | None = None
    for match in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(mil|k)?", text.lower().replace(",", "")):
        value = float(match.group(1))
        if match.group(2):
            value *= 1000
        if value >= 1000:
            best = value if best is None else max(best, value)
    return best


def _lookup_pointer(model: Any, path: str) -> Any:
    node = model
    for part in path.strip("/").split("/"):
        if part == "":
            continue
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None:
            return None
    return node


def resolve_loan_bindings(a2ui: Any, data_model: Any) -> Any:
    """Replace `/loan/...` bindings with resolved values so LoanOffer carries a numeric amount."""

    def visit(node: Any) -> Any:
        if isinstance(node, dict):
            path = node.get("path")
            if set(node.keys()) == {"path"} and isinstance(path, str) and path.startswith("/loan/"):
                value = _lookup_pointer(data_model, path)
                return node if value is None else value
            return {key: visit(value) for key, value in node.items()}
        if isinstance(node, list):
            return [visit(item) for item in node]
        return node

    resolved = []
    for message in a2ui or []:
        if isinstance(message, dict) and "updateComponents" in message:
            body = message["updateComponents"]
            resolved.append(
                {
                    **message,
                    "updateComponents": {
                        **body,
                        "components": [visit(c) for c in body.get("components", [])],
                    },
                }
            )
        else:
            resolved.append(message)
    return resolved


def _has_valid_loan_offer(a2ui: Any) -> bool:
    for message in a2ui or []:
        if not isinstance(message, dict) or "updateComponents" not in message:
            continue
        for component in message["updateComponents"].get("components", []):
            if not isinstance(component, dict) or component.get("component") != "LoanOffer":
                continue
            amount = component.get("amount")
            if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 0:
                return True
            if (
                isinstance(amount, dict)
                and isinstance(amount.get("path"), str)
                and amount["path"].startswith("/loan/")
            ):
                return True
    return False


class LoansConsultService:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        toolbox: Toolbox,
        tracer: Any | None = None,
        deadline_seconds: float = 4.0,
        max_tokens: int = 900,
    ) -> None:
        self._provider = provider
        self._toolbox = toolbox
        self._tracer = tracer
        self._deadline_seconds = deadline_seconds
        self._max_tokens = max_tokens

    def _system_prompt(self, audience: dict[str, Any] | None = None) -> str:
        bank = load_bank_context()
        level = str((audience or {}).get("level") or "standard")
        directive = str((audience or {}).get("directive") or "")
        allowed = ", ".join(_LOANS_COMPONENTS)
        lines = [
            "Eres La Mesa, un asesor de crédito para usuarios en México. Hablas en español (es-MX).",
            "Nunca calcules amortizaciones tú mismo. Si necesitas más información, pregunta y "
            "devuelve terminal_response = null; solo genera terminal_response con confianza > 0.80.",
            "",
            "CONTEXTO DEL BANCO:",
            bank or "(sin contexto bancario configurado; responde de forma conservadora)",
            "",
            "OFERTA DE CRÉDITO (obligatoria en terminal_response): recibirás una 'OFERTA DETERMINISTA' "
            "del motor. La interfaz DEBE incluir LoanOffer con amount, apr, months, monthlyPayment, "
            "totalInterest, totalCost, cat, schedule y action 'request_loan'. Enlaza los números con "
            "bindings a /loan (p. ej. {\"path\": \"/loan/amount\"}, {\"path\": \"/loan/monthlyPayment\"}); "
            "el backend ya colocó los valores en data_model bajo 'loan'. NUNCA inventes montos, tasas ni "
            "pagos. El MONTO siempre debe aparecer.",
            "",
            "FORMAS OBLIGATORIAS:",
            "- action SIEMPRE es un objeto: {\"event\": {\"name\": \"request_loan\", \"context\": {}}}, "
            "nunca una cadena.",
            "- Los props numéricos usan un binding {\"path\": \"/...\"} o un número literal, nunca texto.",
            "- Placeholders {{dot.path}} solo dentro de textos.",
            f"- Usa SOLO estos componentes: {allowed}.",
            "",
        ]
        if directive:
            lines += ["ADAPTACIÓN DE AUDIENCIA (obligatoria): " + directive, ""]
        if level == "simple":
            lines += [
                "MANDATO (audiencia simple): incluye LoanOffer y como máximo un PlanTable corto, "
                "en lenguaje llano. NO incluyas ScenarioComparison, CAT, DTI, gráficas ni panel de riesgo.",
                "El response_text abre con el monto y el pago mensual.",
            ]
        elif level == "detailed":
            lines += [
                "MANDATO (audiencia detallada): incluye ScenarioComparison (escenarios del análisis), "
                "PlanTable, ForecastChart, LineChart, BreakAlert (si el análisis detecta quiebre) y "
                "LoanOffer. Añade la siguiente mejor acción con monto y efecto medido.",
                "El response_text abre con el hallazgo más importante y específico.",
            ]
        else:
            lines += [
                "MANDATO (audiencia estándar): incluye ScenarioComparison, PlanTable y LoanOffer; "
                "menciona la siguiente mejor acción con monto y efecto medido.",
                "El response_text abre con el hallazgo más importante y específico.",
            ]
        lines += [
            "- Deriva todas las cifras del análisis y de la oferta; prohibido inventar o dar consejos genéricos.",
            "",
            "Responde ÚNICAMENTE con un objeto JSON con esta forma:",
            '{"response_text": "texto para hablar", "confidence": 0.0, '
            '"terminal_response": {"catalog_id": "amitie.standard.v1", '
            '"components": [ ...A2UI flat... ], "data_model": { ... }} | null}',
            "",
            "COMPONENTES PERMITIDOS:",
            _describe_allowed(),
            "",
            "ACCIONES PERMITIDAS: " + ", ".join(CATALOG.actions),
            "FORMA (v0.9, flat): cada componente es {\"id\": ..., \"component\": \"Texto\", ...props}.",
        ]
        return "\n".join(lines)

    async def _synthesize(self, text: str, user_id: str) -> dict[str, Any] | None:
        if not text.strip():
            return None
        try:
            result = await self._toolbox.call(
                "synthesize_speech",
                {"text": text, "user_id": user_id, "voice_id": "", "speed": 1.0},
            )
        except Exception:
            return None
        return result if result.get("status") == "ok" else None

    async def _first_name(self, user_id: str) -> str | None:
        try:
            result = await self._toolbox.call("get_profile", {"user_id": user_id})
        except Exception:
            return None
        name = ((result or {}).get("profile") or {}).get("name") or ""
        parts = str(name).strip().split()
        return parts[0] if parts else None

    async def greeting(self, *, user_id: str) -> dict[str, Any]:
        first = await self._first_name(user_id)
        text = f"¿En qué te puedo ayudar hoy, {first}?" if first else GREETING
        audio = await self._synthesize(text, user_id)
        return {
            "status": "ok",
            "response_text": text,
            "audio_id": (audio or {}).get("audio_id"),
            "audio_ref": (audio or {}).get("audio_ref"),
            "terminal_response": None,
        }

    async def consult(
        self,
        *,
        user_id: str,
        text: str,
        loan_request_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        logger.info("loans_consult_started", user_id=user_id, loan_request_id=loan_request_id)
        started = time.perf_counter()
        context = await self._toolbox.call("get_credit_history", {"user_id": user_id})
        analysis = await self._toolbox.call("analyze_loans", {"user_id": user_id})
        audience_result = await self._toolbox.call("get_audience", {"user_id": user_id})
        audience = audience_result.get("audience") if isinstance(audience_result, dict) else None
        requested_amount = _extract_amount(text)
        offer = await self._toolbox.call(
            "compute_loan_offer", {"user_id": user_id, "requested_amount": requested_amount or 0.0}
        )
        await self._toolbox.call(
            "store_loan_offer",
            {
                "loan_request_id": loan_request_id,
                "user_id": user_id,
                "offer": offer.get("offer", offer),
            },
        )
        credit_history = context.get("creditHistory", {}) or {}
        profile = credit_history.get("profile") if isinstance(credit_history, dict) else None
        messages = [
            ChatMessage(role="system", content=self._system_prompt(audience)),
            ChatMessage(
                role="user",
                content=(
                    "Historial de crédito del usuario (JSON):\n"
                    + json.dumps(_compact_credit_history(credit_history), ensure_ascii=False)
                    + "\n\nAudiencia determinista (nivel e instrucciones de complejidad):\n"
                    + json.dumps(audience, ensure_ascii=False)
                    + "\n\nAnalisis determinista (cifras reales; úsalas, no las inventes):\n"
                    + json.dumps(analysis.get("analysis", {}), ensure_ascii=False)
                    + "\n\nOFERTA DETERMINISTA (amount, apr, months, monthlyPayment, totalInterest, "
                    "cat, schedule y riesgo; úsala tal cual en LoanOffer):\n"
                    + json.dumps(offer, ensure_ascii=False)
                    + "\n\nConversación previa:\n"
                    + json.dumps(history or [], ensure_ascii=False)
                    + f"\n\nMensaje del usuario: {text}"
                ),
            ),
        ]

        parsed: dict[str, Any] | None = None
        error: str | None = None
        try:
            generated = await asyncio.wait_for(
                self._provider.generate(
                    messages, response_schema=LOANS_SCHEMA, max_tokens=self._max_tokens
                ),
                timeout=self._deadline_seconds,
            )
            parsed = _parse_json(generated.text)
            validation = self._validate_terminal(parsed, loan_request_id)
            if validation is not None:
                error = validation
                parsed = None
        except (ProviderError, asyncio.TimeoutError, TimeoutError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        response_text = ""
        confidence = 0.0
        terminal: dict[str, Any] | None = None
        if parsed is not None:
            response_text = str(parsed.get("response_text") or "").strip()
            confidence = float(parsed.get("confidence") or 0.0)
            terminal = parsed.get("terminal_response")

        # Deterministic safety net (≤5s SLA): timeout, provider error, invalid output,
        # or a low-confidence terminal all fall back to an engine-built interface.
        if parsed is None or (terminal is not None and confidence <= CONFIDENCE_THRESHOLD):
            fallback = loans_fallback.build_terminal(
                profile=profile, audience=audience, offer=offer, analysis=analysis
            )
            if not response_text:
                response_text = str(fallback.get("response_text") or "")
            if fallback.get("terminal_response") is not None:
                terminal = fallback["terminal_response"]
                confidence = 1.0
            elif parsed is None:
                terminal = None

        if not response_text:
            response_text = "No pude generar la propuesta en este momento. Intenta de nuevo."

        terminal_payload: dict[str, Any] | None = None
        if terminal is not None:
            propose = offer.get("offer", offer) if isinstance(offer, dict) else {}
            terms = propose.get("offer", {}) if isinstance(propose, dict) else {}
            terminal.setdefault("data_model", {})
            if isinstance(terminal["data_model"], dict):
                if isinstance(audience, dict):
                    terminal["data_model"]["audience"] = audience
                terminal["data_model"]["loan"] = {
                    **terms,
                    "schedule": propose.get("schedule", []) if isinstance(propose, dict) else [],
                    "risk": propose.get("risk", {}) if isinstance(propose, dict) else {},
                    "warnings": propose.get("warnings", []) if isinstance(propose, dict) else [],
                }
            persisted = await self._persist_terminal(terminal, user_id, loan_request_id)
            if persisted is not None:
                terminal_payload = persisted

        audio = await self._synthesize(response_text, user_id)
        await self._trace(started, error=None)
        logger.info(
            "loans_consult_completed",
            user_id=user_id,
            loan_request_id=loan_request_id,
            confidence=confidence,
            has_terminal_response=terminal_payload is not None,
        )
        return {
            "status": "ok",
            "loan_request_id": loan_request_id,
            "response_text": response_text,
            "confidence": confidence,
            "audio_id": (audio or {}).get("audio_id"),
            "audio_ref": (audio or {}).get("audio_ref"),
            "terminal_response": terminal_payload,
        }

    def _validate_terminal(
        self, parsed: dict[str, Any], loan_request_id: str
    ) -> str | None:
        if not isinstance(parsed.get("response_text"), str):
            return "falta response_text"
        terminal = parsed.get("terminal_response")
        if terminal is None:
            return None
        if not isinstance(terminal, dict) or not isinstance(terminal.get("components"), list):
            return "terminal_response debe incluir components"
        terminal["components"] = normalize_components(terminal["components"])
        catalog_id = terminal.get("catalog_id") or CATALOG.catalog_id
        result = validate_messages(
            [
                {"version": CATALOG.version, "createSurface": {"surfaceId": "pending", "catalogId": catalog_id}},
                {"version": CATALOG.version, "updateComponents": {"surfaceId": "pending", "components": terminal["components"]}},
            ]
        )
        if not result.ok:
            return "; ".join(result.issues)
        types = {
            component.get("component")
            for component in terminal["components"]
            if isinstance(component, dict)
        }
        if "LoanOffer" not in types:
            return "terminal_response debe incluir el componente LoanOffer"
        if not _has_valid_loan_offer(
            [{"updateComponents": {"components": terminal["components"]}}]
        ):
            return "LoanOffer debe incluir amount (numérico o enlace a /loan/amount)"
        return None

    async def _persist_terminal(
        self, terminal: dict[str, Any], user_id: str, loan_request_id: str
    ) -> dict[str, Any] | None:
        persisted = await self._toolbox.call(
            "persist_ui",
            {
                "user_id": user_id,
                "domain": "loans_credits",
                "catalog_id": terminal.get("catalog_id") or CATALOG.catalog_id,
                "components": terminal.get("components", []),
                "data_model": terminal.get("data_model") or {},
                "entity_id": loan_request_id,
                "simulation": terminal.get("simulation"),
            },
        )
        if persisted.get("status") != "ok":
            return None
        surface_id = persisted.get("surface_id")
        hydrated = await self._toolbox.call("hydrate_ui", {"surface_id": surface_id})
        a2ui = hydrated.get("a2ui", persisted.get("a2ui", []))
        data_model: Any = {}
        for message in a2ui:
            if isinstance(message, dict) and "updateDataModel" in message:
                data_model = message["updateDataModel"].get("value") or {}
                break
        a2ui = resolve_loan_bindings(a2ui, data_model)
        if not _has_valid_loan_offer(a2ui):
            return None
        return {
            "catalog_id": persisted.get("catalog_id"),
            "surface_id": surface_id,
            "a2ui": a2ui,
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
                name="loans_consult",
                provider=getattr(self._provider, "name", "gateway"),
                model=getattr(self._provider, "model", None),
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=error,
            ),
        )
