"""El Reves: two-persona loan negotiation over the in-process MCP toolbox.

One ADK agent is used per persona (instruction swapped per turn); every round is
recorded through MCP and emitted as A2UI via `persist_ui`.
"""

from __future__ import annotations

import json
from typing import Any

from google.adk.agents.llm_agent import Agent
from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types

from mcp_servers.toolbox import Toolbox
from providers.base import LLMProvider, ProviderError
from ui_contract.catalog import CATALOG_ID

from .model import GatewayLlm, ModelCallLimitError
from .speech import SpeechEnricher
from .tools import build_adk_tools

APP_NAME = "el_reves"
MAX_ROUNDS = 3

BANK_INSTRUCTION = (
    "Eres el negociador del banco en 'El Reves'. Habla en espanol. "
    "Usa get_lender_policies y generate_offer para construir una oferta dentro de los limites "
    "del banco (nunca inventes cifras). Registra tu ronda con "
    "record_negotiation_round(actor='bank', offer=<terminos>), luego llama get_negotiation y emite "
    "EXACTAMENTE una superficie con persist_ui que incluya un OfferCard (actor='bank', headline, "
    "terms={{apr, months, monthlyPayment, totalCost}}) y un NegotiationTranscript (rounds). "
    "No escribas la interfaz en texto."
)

ADVOCATE_INSTRUCTION = (
    "Eres el defensor del usuario en 'El Reves'. Habla en espanol. "
    "Usa evaluate_offer para verificar que la oferta del banco sea realmente pagable; si no lo es, "
    "contraoferta proponiendo terminos mas favorables. Registra tu ronda con "
    "record_negotiation_round(actor='advocate', offer=<terminos|contraoferta>), luego llama "
    "get_negotiation y emite EXACTAMENTE una superficie con persist_ui que incluya un OfferCard "
    "(actor='advocate') y un NegotiationTranscript (rounds). No escribas la interfaz en texto."
)

FINAL_COMPONENTS: list[dict[str, Any]] = [
    {"id": "root", "component": "Column", "children": ["title", "plan", "next"], "gap": 12},
    {"id": "title", "component": "Heading", "text": "Plan confirmado"},
    {
        "id": "plan",
        "component": "PlanTable",
        "months": {"path": "/plan/months"},
        "breakMonth": {"path": "/plan/breakMonth"},
    },
    {
        "id": "next",
        "component": "Text",
        "text": "Proximos pasos: firma el convenio digital y revisa tu primer pago en la app.",
    },
]


class NegotiationService:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        toolbox: Toolbox,
        tracer: Any | None = None,
        max_model_calls: int = 6,
        max_rounds: int = MAX_ROUNDS,
    ) -> None:
        self._toolbox = toolbox
        self._tracer = tracer
        self._max_calls = max_model_calls
        self._max_rounds = max_rounds
        self._model = GatewayLlm(model="gateway", provider=provider, max_calls=max_model_calls)
        self._speech = SpeechEnricher(toolbox)
        self._tools: list[Any] | None = None
        self._captured: dict[str, dict[str, Any]] = {}

    async def _ensure_tools(self) -> list[Any]:
        if self._tools is None:
            self._tools = await build_adk_tools(self._toolbox, on_result=self._capture)
        return self._tools

    def _capture(self, name: str, result: dict[str, Any]) -> None:
        if name == "persist_ui":
            self._captured[name] = result

    async def run_round(
        self,
        *,
        session_id: str,
        user_id: str,
        position: dict[str, Any] | None = None,
        take_control: bool = False,
    ) -> dict[str, Any]:
        session = await self._toolbox.call("get_session", {"session_id": session_id})
        if session.get("status") != "ok":
            return {
                "status": "error",
                "error_code": "negotiation_error",
                "retryable": False,
                "issues": session.get("issues", ["unknown session"]),
            }
        negotiation = dict((session.get("context") or {}).get("negotiation") or {})
        rounds = (await self._toolbox.call("get_negotiation", {"session_id": session_id}))["rounds"]

        if len(rounds) >= self._max_rounds:
            return {
                "status": "error",
                "error_code": "negotiation_error",
                "retryable": False,
                "issues": [f"negotiation reached max rounds ({self._max_rounds})"],
            }

        if take_control:
            await self._toolbox.call(
                "record_negotiation_round",
                {"session_id": session_id, "actor": "user", "offer": position or {}},
            )
            negotiation["take_control"] = True
            rounds = (
                await self._toolbox.call("get_negotiation", {"session_id": session_id})
            )["rounds"]
            actor = "bank"
        else:
            last_actor = rounds[-1]["actor"] if rounds else "user"
            actor = "bank" if negotiation.get("take_control") or last_actor != "bank" else "advocate"

        surface = await self._run_persona(
            actor=actor,
            session_id=session_id,
            user_id=user_id,
            rounds=rounds,
            position=position,
        )
        if surface.get("status") != "ok":
            return surface

        rounds = (await self._toolbox.call("get_negotiation", {"session_id": session_id}))["rounds"]
        negotiation.update({"round": len(rounds), "last_actor": actor, "status": "open"})
        await self._toolbox.call(
            "set_session_context",
            {"session_id": session_id, "context": {"negotiation": negotiation}},
        )
        return {
            "status": "ok",
            "actor": actor,
            "round": len(rounds),
            "surface_id": surface.get("surface_id"),
            "a2ui": surface.get("a2ui", []),
            "audio_ref": surface.get("audio_ref"),
            "assistant_text": "",
        }

    async def _run_persona(
        self,
        *,
        actor: str,
        session_id: str,
        user_id: str,
        rounds: list[dict[str, Any]],
        position: dict[str, Any] | None,
    ) -> dict[str, Any]:
        tools = await self._ensure_tools()
        instruction = BANK_INSTRUCTION if actor == "bank" else ADVOCATE_INSTRUCTION
        agent = Agent(
            name=f"el_reves_{actor}", model=self._model, instruction=instruction, tools=tools
        )
        runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
        await runner.session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )

        message = (
            f"user_id: {user_id}\nsession_id: {session_id}\nactor: {actor}\n"
            f"rondas previas: {json.dumps(rounds, ensure_ascii=False)}\n"
            f"posicion del usuario: {json.dumps(position or {}, ensure_ascii=False)}\n"
            "Registra tu ronda, llama get_negotiation y emite la superficie solicitada."
        )
        self._model.reset_calls()
        self._captured.clear()
        error: str | None = None
        try:
            async for _ in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(role="user", parts=[types.Part.from_text(text=message)]),
                run_config=RunConfig(max_llm_calls=self._max_calls),
            ):
                pass
        except ModelCallLimitError as exc:
            error = str(exc)
        except ProviderError as exc:
            error = str(exc)
        except Exception as exc:  # keep the API resilient
            error = f"{type(exc).__name__}: {exc}"

        if error is not None:
            return {
                "status": "error",
                "error_code": "provider_unavailable",
                "retryable": True,
                "message": error,
            }

        captured = self._captured.get("persist_ui")
        if captured is None or captured.get("status") != "ok":
            return {
                "status": "error",
                "error_code": "agent_error",
                "retryable": True,
                "issues": (captured or {}).get("issues", ["the persona did not call persist_ui"]),
            }
        return await self._speech.enrich(captured, user_id=user_id)

    async def accept(
        self, *, session_id: str, user_id: str, offer: dict[str, Any]
    ) -> dict[str, Any]:
        ack = await self._toolbox.call("accept_offer", {"user_id": user_id, "offer": offer})
        if ack.get("status") != "ok":
            return {
                "status": "error",
                "error_code": "negotiation_error",
                "retryable": False,
                "issues": ack.get("issues", ["offer rejected"]),
            }

        await self._toolbox.call(
            "set_session_context",
            {
                "session_id": session_id,
                "context": {"negotiation": {"status": "accepted", "offer": offer}},
            },
        )
        persisted = await self._toolbox.call(
            "persist_ui",
            {
                "user_id": user_id,
                "domain": "loans_credits",
                "catalog_id": CATALOG_ID,
                "components": FINAL_COMPONENTS,
                "data_model": {},
                "simulation": {"offer": offer},
            },
        )
        if persisted.get("status") != "ok":
            return {
                "status": "error",
                "error_code": "agent_error",
                "retryable": True,
                "issues": persisted.get("issues", ["could not persist"]),
            }
        persisted = await self._speech.enrich(persisted, user_id=user_id)
        return {
            "status": "ok",
            "surface_id": persisted.get("surface_id"),
            "a2ui": persisted.get("a2ui", []),
            "audio_ref": persisted.get("audio_ref"),
            "assistant_text": "Plan confirmado.",
        }
