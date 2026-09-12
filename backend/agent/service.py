"""Agent turn service: ADK orchestrator over the in-process MCP toolbox."""

from __future__ import annotations

import json
import time
from typing import Any

from google.adk.agents.llm_agent import Agent
from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types

from mcp_servers.toolbox import Toolbox
from observability.context import current_trace_id
from observability.tracing import Tracer, TraceEvent, new_trace_id
from providers.base import LLMProvider, ProviderError
from ui_contract.prompt import build_system_prompt

from .model import GatewayLlm, ModelCallLimitError
from .speech import SpeechEnricher
from .tools import build_adk_tools

APP_NAME = "lamina"
AGENT_NAME = "lamina"

ROLE_DESCRIPTION = (
    "Eres La Mesa, un agente financiero para usuarios en México. Diagnosticas su "
    "situación y decides qué interfaz necesita el usuario, ya sea para resolver deudas "
    "o para planear una meta de ahorro."
)
UI_DESCRIPTION = (
    "Tienes dos flujos. Decide cuál aplica según el mensaje del usuario y usa SOLO las "
    "herramientas MCP disponibles; nunca calcules números tú mismo.\n"
    "FLUJO DEUDA (La Mesa + El Revés): (1) llama get_financial_context con el user_id; "
    "(2) simula con simulate_plan (elige estrategia) y confirma con detect_plan_breaks; "
    "(3) si el plan se rompe, DEBES emitir proactivamente BreakAlert + PlanTable; "
    "(4) si el usuario pide un ajuste, vuelve a simular y reemite la superficie sin "
    "BreakAlert si ya no se rompe; (5) emite EXACTAMENTE una superficie con persist_ui, "
    "con domain='loans_credits' e incluye el objeto simulation (strategy, extra_payment, "
    "extra_income, expense_reduction, horizon_months, events).\n"
    "FLUJO AHORRO (Saving Bags): si el usuario menciona una meta (ej. 'viaje a Japón'), "
    "(1) llama create_bag con el nombre y, si los da, target_amount/target_date; "
    "(2) infiere tú mismo las preguntas necesarias (fechas, días, viajeros, estilo, origen) "
    "y emite un formulario con TextField/ChoiceGroup y persist_ui, domain='saving_bag', "
    "entity_id=bag_id; (3) cuando el usuario responda, guarda con answer_bag, luego llama "
    "research_costs, estimate_total y compute_feasibility; (4) emite la superficie del plan "
    "con persist_ui (domain='saving_bag', entity_id=bag_id); (5) si el plan no alcanza "
    "(redirect.recommended), ofrece un préstamo con OfferCard y, al aceptar, continúa el "
    "flujo de deuda (accept_offer) hacia La Mesa. Usa refresh_bag solo si el usuario pide "
    "actualizar costos.\n"
    "CAJA DE CRISTAL: si la acción es 'toggle_assumption' (el usuario editó una suposición del "
    "panel '¿Por qué ves esto?'), aplica el nuevo valor (extra_income/extra_payment/"
    "expense_reduction en deuda, o answer_bag con days/travelers en ahorro), vuelve a simular "
    "o recalcular y reemite la superficie con persist_ui. El panel de suposiciones se "
    "reconstruye automáticamente.\n"
    "En ambos flujos el paso final es SIEMPRE una única llamada a persist_ui. No escribas "
    "la interfaz en texto; el texto es solo para el usuario."
)


class AgentService:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        toolbox: Toolbox,
        tracer: Tracer | None = None,
        max_model_calls: int = 10,
    ) -> None:
        self._toolbox = toolbox
        self._tracer = tracer
        self._max_calls = max_model_calls
        self._model = GatewayLlm(model="gateway", provider=provider, max_calls=max_model_calls)
        self._speech = SpeechEnricher(toolbox)
        self._runner: InMemoryRunner | None = None
        self._captured: dict[str, dict[str, Any]] = {}

    async def _ensure_runner(self) -> InMemoryRunner:
        if self._runner is None:
            tools = await build_adk_tools(self._toolbox, on_result=self._capture)
            agent = Agent(
                name=AGENT_NAME,
                model=self._model,
                instruction=build_system_prompt(
                    role_description=ROLE_DESCRIPTION, ui_description=UI_DESCRIPTION
                ),
                tools=tools,
            )
            self._runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
        return self._runner

    def _capture(self, name: str, result: dict[str, Any]) -> None:
        if name == "persist_ui":
            self._captured[name] = result

    async def _ensure_session(
        self, runner: InMemoryRunner, session_id: str, user_id: str
    ) -> None:
        session = await runner.session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if session is None:
            await runner.session_service.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )

    async def run_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        text: str | None = None,
        action: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        runner = await self._ensure_runner()
        await self._ensure_session(runner, session_id, user_id)

        if action is not None:
            payload = {
                "user_id": user_id,
                "action": action.get("name"),
                "surface_id": action.get("surface_id"),
                "context": action.get("context", {}),
            }
            message_text = (
                "El usuario interactuó con la interfaz. Contexto de la acción: "
                + json.dumps(payload, ensure_ascii=False)
            )
        else:
            message_text = f"user_id: {user_id}\nMensaje del usuario: {text or ''}"

        self._model.reset_calls()
        self._captured.clear()
        assistant_texts: list[str] = []
        error: str | None = None
        error_code = "agent_error"
        retryable = False
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part.from_text(text=message_text)]
                ),
                run_config=RunConfig(max_llm_calls=self._max_calls),
            ):
                for part in getattr(event.content, "parts", None) or []:
                    if getattr(part, "text", None):
                        assistant_texts.append(part.text)
        except ModelCallLimitError as exc:
            error = str(exc)
            error_code = "model_call_limit"
            retryable = True
        except ProviderError as exc:
            error = str(exc)
            error_code = "provider_unavailable"
            retryable = True
        except Exception as exc:  # keep the API resilient to ADK/tool failures
            error = f"{type(exc).__name__}: {exc}"

        assistant_text = "\n".join(text for text in assistant_texts if text).strip()
        await self._trace(started, error=error)

        if error is not None:
            return {
                "status": "error",
                "error_code": error_code,
                "retryable": retryable,
                "message": error,
                "assistant_text": assistant_text,
            }

        captured = self._captured.get("persist_ui")
        if captured is None:
            return {
                "status": "error",
                "error_code": "agent_error",
                "retryable": True,
                "issues": ["the agent did not call persist_ui"],
                "assistant_text": assistant_text,
            }
        if captured.get("status") != "ok":
            return {
                "status": "error",
                "error_code": "agent_error",
                "retryable": True,
                "issues": captured.get("issues", []),
                "assistant_text": assistant_text,
            }
        captured = await self._speech.enrich(captured, user_id=user_id)
        return {
            "status": "ok",
            "surface_id": captured.get("surface_id"),
            "a2ui": captured.get("a2ui", []),
            "catalog_id": captured.get("catalog_id"),
            "audio_ref": captured.get("audio_ref"),
            "assistant_text": assistant_text,
        }

    async def _trace(self, started: float, *, error: str | None) -> None:
        if self._tracer is None:
            return
        trace_id = current_trace_id() or new_trace_id()
        await self._tracer.record(
            trace_id,
            TraceEvent(
                kind="agent",
                name="turn",
                provider=getattr(self._model.provider, "name", "gateway"),
                model=self._model.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=error,
            ),
        )
