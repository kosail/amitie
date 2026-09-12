"""Voice-first loans & credits consult (single structured LLM call).

See `LOANS_CONSULT_GUIDE.md`. One model call returns
`{response_text, confidence, terminal_response}`; the terminal UI is persisted
(placeholders + loan association) only when confidence > 0.80, and the spoken
answer is always synthesized to mp3.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from mcp_servers.toolbox import Toolbox
from providers.base import ChatMessage, LLMProvider, ProviderError
from ui_contract.catalog import CATALOG
from ui_contract.prompt import describe_components
from ui_contract.validator import validate_messages

from .bank_context import load_bank_context

CONFIDENCE_THRESHOLD = 0.80
MAX_ATTEMPTS = 2

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


class LoansConsultService:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        toolbox: Toolbox,
        tracer: Any | None = None,
    ) -> None:
        self._provider = provider
        self._toolbox = toolbox
        self._tracer = tracer

    def _system_prompt(self) -> str:
        bank = load_bank_context()
        return "\n".join(
            [
                "Eres La Mesa, un asesor de crédito para usuarios en México. Hablas en español (es-MX).",
                "Tu objetivo es entender la necesidad del usuario y, cuando tengas suficiente "
                "contexto, proponer una interfaz A2UI. Nunca calcules amortizaciones tú mismo.",
                "",
                "CONTEXTO DEL BANCO:",
                bank or "(sin contexto bancario configurado; responde de forma conservadora)",
                "",
                "Si necesitas más información, pregunta y devuelve terminal_response = null.",
                "Solo genera terminal_response cuando la confianza sea mayor a 0.80.",
                "En los componentes usa placeholders {{dot.path}} para datos importantes "
                "(por ejemplo {{loan.amount}}) y coloca sus valores en data_model.",
                "",
                "Responde ÚNICAMENTE con un objeto JSON con esta forma:",
                '{"response_text": "texto para hablar", "confidence": 0.0, '
                '"terminal_response": {"catalog_id": "amitie.standard.v1", '
                '"components": [ ...A2UI flat... ], "data_model": { ... }} | null}',
                "",
                "COMPONENTES PERMITIDOS:",
                describe_components(CATALOG),
                "",
                "ACCIONES PERMITIDAS: " + ", ".join(CATALOG.actions),
                "FORMA (v0.9, flat): cada componente es {\"id\": ..., \"component\": \"Texto\", ...props}.",
            ]
        )

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

    async def greeting(self, *, user_id: str) -> dict[str, Any]:
        audio = await self._synthesize(GREETING, user_id)
        return {
            "status": "ok",
            "response_text": GREETING,
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
        started = time.perf_counter()
        context = await self._toolbox.call("get_credit_history", {"user_id": user_id})
        messages = [
            ChatMessage(role="system", content=self._system_prompt()),
            ChatMessage(
                role="user",
                content=(
                    "Historial de crédito del usuario (JSON):\n"
                    + json.dumps(context.get("creditHistory", {}), ensure_ascii=False)
                    + "\n\nConversación previa:\n"
                    + json.dumps(history or [], ensure_ascii=False)
                    + f"\n\nMensaje del usuario: {text}"
                ),
            ),
        ]

        parsed: dict[str, Any] | None = None
        error: str | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                result = await self._provider.generate(messages, response_schema=LOANS_SCHEMA)
                parsed = _parse_json(result.text)
                validation = self._validate_terminal(parsed, loan_request_id)
                if validation is None:
                    break
                error = validation
                messages = messages + [
                    ChatMessage(
                        role="user",
                        content=f"Tu respuesta no fue válida: {validation}. Corrige y responde de nuevo.",
                    )
                ]
            except ProviderError as exc:
                error = str(exc)
                break
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                break

        if parsed is None:
            await self._trace(started, error=error)
            return {
                "status": "error",
                "error_code": "agent_error",
                "retryable": True,
                "message": error or "no se pudo interpretar la respuesta",
            }

        response_text = str(parsed.get("response_text") or "").strip()
        confidence = float(parsed.get("confidence") or 0.0)
        terminal = parsed.get("terminal_response")

        terminal_payload: dict[str, Any] | None = None
        if terminal and confidence > CONFIDENCE_THRESHOLD:
            persisted = await self._persist_terminal(terminal, user_id, loan_request_id)
            if persisted is not None:
                terminal_payload = persisted

        audio = await self._synthesize(response_text, user_id)
        await self._trace(started, error=None)
        return {
            "status": "ok",
            "loan_request_id": loan_request_id,
            "response_text": response_text,
            "confidence": confidence,
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
        catalog_id = terminal.get("catalog_id") or CATALOG.catalog_id
        result = validate_messages(
            [
                {"version": CATALOG.version, "createSurface": {"surfaceId": "pending", "catalogId": catalog_id}},
                {"version": CATALOG.version, "updateComponents": {"surfaceId": "pending", "components": terminal["components"]}},
            ]
        )
        return "; ".join(result.issues) if not result.ok else None

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
        return {
            "catalog_id": persisted.get("catalog_id"),
            "surface_id": persisted.get("surface_id"),
            "a2ui": persisted.get("a2ui", []),
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
