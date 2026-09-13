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
from typing import Any, Mapping

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
    "Hola, soy Luna, tu asesora de crédito. Cuéntame qué necesitas: "
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


class _Term:
    MIN = 6
    MAX = 48


_WORD_YEARS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}
_AFFIRMATIVE = (
    "si",
    "claro",
    "confirmo",
    "confirmado",
    "correcto",
    "de acuerdo",
    "adelante",
    "esta bien",
    "ok",
    "okay",
    "va",
    "acepto",
    "hagamoslo",
)
_NEGATIVE = ("no", "mejor no", "otro plazo", "cambiar", "cambia", "cambiale", "espera", "no quiero")


def _strip_accents(text: str) -> str:
    import unicodedata

    return "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )


def _extract_term(text: str) -> int | None:
    """Deterministic requested term in months from the user's message (6–48)."""
    if not text:
        return None
    lowered = _strip_accents(text.lower())
    if re.search(r"\banos?\s+y\s+medio\b", lowered):
        return 18
    month_match = re.search(r"(\d+)\s*mes(?:es)?\b", lowered)
    if month_match:
        months = int(month_match.group(1))
        return months if _Term.MIN <= months <= _Term.MAX else None
    year_match = re.search(r"(\d+)\s*anos?\b", lowered)
    if year_match:
        months = int(year_match.group(1)) * 12
        return months if _Term.MIN <= months <= _Term.MAX else None
    for word, value in _WORD_YEARS.items():
        if re.search(rf"\b{word}\s+anos?\b", lowered):
            months = value * 12
            return months if _Term.MIN <= months <= _Term.MAX else None
    return None


def _matches_any(text: str, phrases: tuple[str, ...]) -> bool:
    if not text:
        return False
    lowered = _strip_accents(text.lower())
    return any(
        re.search(rf"\b{re.escape(_strip_accents(phrase))}\b", lowered) for phrase in phrases
    )


def _is_affirmative(text: str) -> bool:
    return _matches_any(text, _AFFIRMATIVE)


def _is_negative(text: str) -> bool:
    return _matches_any(text, _NEGATIVE)


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "$0"


# The user explicitly asking for the ceiling lets us offer the engine maximum.
_MAX_INTENT = (
    "el maximo",
    "lo maximo",
    "la cantidad maxima",
    "el monto maximo",
    "lo mas que puedas",
    "lo mas que me puedas",
    "lo que me puedas dar",
    "lo que me puedas prestar",
    "lo que me ofrezcas",
    "lo que sea posible",
    "tu dime",
    "lo que consideres",
    "tu sabras",
)

_PURPOSE_PATTERNS = (
    r"para ([^.,;!?]{3,60})",
    r"usarl[oa] para ([^.,;!?]{3,60})",
)
_PURPOSE_STOPWORDS = {"que", "quien", "cuando", "donde", "como", "cual", "cuanto"}
_PURPOSE_PRONOUNS = {"mi", "ti", "si", "esto", "eso"}


def _wants_max(text: str) -> bool:
    return _matches_any(text, _MAX_INTENT)


# "It's private" / "prefer not to say" — we stop asking and never research it.
_PRIVATE_INTENT = (
    "es privado",
    "es personal",
    "prefiero no decir",
    "prefiero no decirlo",
    "no quiero decir",
    "no quiero decirlo",
    "sin decir",
    "no te lo puedo decir",
    "no lo quiero compartir",
    "es confidencial",
    "privado",
    "razón privada",
    "razon privada",
)


def _wants_private(text: str) -> bool:
    return _matches_any(text, _PRIVATE_INTENT)


def _extract_purpose(text: str) -> str | None:
    """Best-effort purpose from "para ..." phrasing; the answer stays conversational."""
    if not text:
        return None
    lowered = _strip_accents(text.lower())
    for pattern in _PURPOSE_PATTERNS:
        match = re.search(pattern, lowered)
        if not match:
            continue
        phrase = match.group(1).strip()
        if phrase and phrase.split()[0] not in _PURPOSE_STOPWORDS and phrase not in _PURPOSE_PRONOUNS:
            return phrase
    return None


# Prompt-size trims (latency): only what the mandates actually use, and no long
# per-month schedule (the model binds `/loan/schedule` instead).
_ANALYSIS_KEYS = ("nextBestAction", "behavior", "quincena", "highCost")
_HISTORY_LIMIT = 8


def _trimmed_analysis(analysis: Any) -> dict[str, Any]:
    payload = (analysis or {}).get("analysis") if isinstance(analysis, Mapping) else None
    if not isinstance(payload, Mapping):
        return {}
    return {key: payload[key] for key in _ANALYSIS_KEYS if payload.get(key) is not None}


def _offer_for_prompt(offer: Any) -> Any:
    """Recursively drop the long per-month schedule; the model binds /loan/schedule."""

    def trim(value: Any) -> Any:
        if isinstance(value, Mapping):
            result: dict[str, Any] = {}
            for key, item in value.items():
                if key == "schedule" and isinstance(item, list):
                    result[key] = f"({len(item)} cuotas; usa el binding /loan/schedule)"
                else:
                    result[key] = trim(item)
            return result
        if isinstance(value, list):
            return [trim(item) for item in value]
        return value

    return trim(offer) if isinstance(offer, Mapping) else offer


def _recent_history(history: Any, limit: int = _HISTORY_LIMIT) -> list[Any]:
    return list(history or [])[-limit:]


def _confirmation_text(offer: Mapping[str, Any], requested_term: int, name: str | None) -> str:
    """Explain the real implications of the user's chosen term and ask to confirm."""
    options = {
        int(option["months"]): option
        for option in (offer.get("options") or [])
        if isinstance(option, Mapping) and option.get("months")
    }
    requested = options.get(requested_term)
    if requested is None:
        return (
            f"El plazo mínimo es {_Term.MIN} meses y el máximo {_Term.MAX}. "
            f"¿Qué plazo prefieres?"
        )
    engine_months = int(
        (offer.get("recommendation") or {}).get("engineRecommended")
        or (offer.get("recommendation") or {}).get("months")
        or requested_term
    )
    recommended = options.get(engine_months)
    capacity = offer.get("capacity") or {}
    income = float(capacity.get("income") or 0.0)
    max_payment = float(capacity.get("maxPayment") or 0.0)
    payment = float(requested.get("monthlyPayment") or 0.0)
    interest = float(requested.get("totalInterest") or 0.0)
    prefix = f"{name}, " if name else ""
    parts = [f"{prefix}entiendo que quieres tu crédito a {requested_term} meses."]
    if income > 0:
        parts.append(
            f"Tu pago mensual sería {_money(payment)} ({payment / income * 100:.0f}% de tu ingreso) "
            f"y pagarías {_money(interest)} de intereses en total."
        )
    else:
        parts.append(
            f"Tu pago mensual sería {_money(payment)} y pagarías {_money(interest)} de intereses."
        )
    if recommended is not None and engine_months != requested_term:
        parts.append(
            f"A {engine_months} meses tu pago sería {_money(recommended.get('monthlyPayment'))} "
            f"e intereses {_money(recommended.get('totalInterest'))}."
        )
    if max_payment > 0 and payment > max_payment + 0.5:
        parts.append(
            f"Ese pago supera tu capacidad de pago (~{_money(max_payment)}), así que no sería prudente."
        )
        parts.append(f"¿Prefieres {engine_months} meses o ajustamos el monto?")
    else:
        parts.append(f"¿Confirmas que quieres {requested_term} meses? Responde \"sí\" para continuar.")
    return " ".join(parts)


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
        deadline_seconds: float = 6.5,
        intake_deadline_seconds: float = 3.5,
        max_tokens: int = 1500,
    ) -> None:
        self._provider = provider
        self._toolbox = toolbox
        self._tracer = tracer
        self._deadline_seconds = deadline_seconds
        self._intake_deadline_seconds = intake_deadline_seconds
        self._max_tokens = max_tokens

    def _system_prompt(self, audience: dict[str, Any] | None = None, *, intake: bool = False) -> str:
        bank = load_bank_context()
        role = (
            "Eres Luna, una asesora de crédito para usuarios en México. Hablas en español (es-MX). "
            "Tu nombre es Luna. Eres femenina; si te presentas o te refieres a ti misma usa el "
            "femenino (p. ej. \"soy tu asesora\"). No digas tu nombre salvo que sea necesario."
        )
        if intake:
            return "\n".join(
                [
                    role,
                    "",
                    "CONTEXTO DEL BANCO:",
                    bank or "(sin contexto bancario configurado; responde de forma conservadora)",
                    "",
                    "ESTÁS EN CONVERSACIÓN, AÚN SIN OFERTA: al usuario todavía le falta dar el monto "
                    "y/o el propósito. Responde de forma natural y breve (una o dos frases): reconoce lo "
                    "que ya dijo, no repitas la bienvenida, y pregunta con calidez solo lo que falte. Si "
                    "preguntas el propósito, indícale que puede responder \"es privado\" y no volverás a "
                    "preguntar. NO generes una oferta, NO calcules cifras y devuelve terminal_response = "
                    "null. El monto mínimo del producto es 5,000 MXN.",
                    "",
                    "Responde ÚNICAMENTE con un objeto JSON: "
                    '{"response_text": "texto para hablar", "confidence": 0.0, "terminal_response": null}',
                ]
            )
        level = str((audience or {}).get("level") or "standard")
        directive = str((audience or {}).get("directive") or "")
        allowed = ", ".join(_LOANS_COMPONENTS)
        lines = [
            role,
            "Nunca calcules amortizaciones tú mismo. Si necesitas más información, pregunta y "
            "devuelve terminal_response = null; solo genera terminal_response con confianza > 0.80.",
            "",
            "CONTEXTO DEL BANCO:",
            bank or "(sin contexto bancario configurado; responde de forma conservadora)",
            "",
            "OFERTA DE CRÉDITO: el motor ya calculó una 'OFERTA DETERMINISTA' porque el usuario ya dio "
            "un monto (o pidió el máximo). La interfaz DEBE incluir LoanOffer con amount, apr, months, "
            "monthlyPayment, totalInterest, totalCost, cat, schedule y action 'request_loan'. Enlaza los "
            "números con bindings a /loan (p. ej. {\"path\": \"/loan/amount\"}); el backend ya colocó los "
            "valores en data_model bajo 'loan'. NUNCA inventes montos, tasas ni pagos.",
            "OPCIONES DE PLAZO: la oferta incluye `options` (plazos acordes al monto, no siempre los "
            "mismos; p. ej. montos pequeños usan plazos cortos), cada una con su pago mensual e interés "
            "total del motor, y una `recommendation` con el plazo elegido (`months`) y su razón. Para "
            "ScenarioComparison usa SOLO esas opciones (label \"N meses\", monthlyPayment, "
            "payoffMonths = meses, totalInterest) y resalta la que trae recommended=true. Menciona en "
            "response_text por qué se eligió ese plazo (usa `recommendation.reason` o, si el usuario lo "
            "pidió, reconócelo). El backend sobreescribe estos valores con el motor; no uses los "
            "escenarios de deuda del análisis para las opciones de plazo.",
            "CONSISTENCIA: toma en cuenta los mensajes previos y el estado de la conversación. Si el "
            "usuario pidió un plazo específico, respétalo: la oferta ya viene a ESE plazo "
            "(`offer.termMonths` / `recommendation.months`); nunca lo cambies ni lo ignores.",
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
        lines += [
            "SI AÚN NO HAY MONTO (ni el usuario pidió el máximo), NO generes terminal_response: pregunta "
            "con naturalidad cuánto necesita y para qué, y devuelve null. Lo siguiente aplica solo cuando "
            "ya tengas el monto:",
            "",
        ]
        if level == "simple":
            lines += [
                "MANDATO (audiencia simple): incluye LoanOffer y, como comparación de plazos, "
                "ScenarioComparison con las opciones de la oferta (`options`), en lenguaje llano. "
                "NO incluyas CAT, DTI, gráficas ni panel de riesgo.",
                "El response_text abre con el monto y el pago mensual.",
            ]
        elif level == "detailed":
            lines += [
                "MANDATO (audiencia detallada): incluye ScenarioComparison con las opciones de plazo de "
                "la oferta (`options`), PlanTable, ForecastChart, LineChart, BreakAlert (si el análisis "
                "detecta quiebre) y LoanOffer. Añade la siguiente mejor acción con monto y efecto medido.",
                "El response_text abre con el hallazgo más importante y específico.",
            ]
        else:
            lines += [
                "MANDATO (audiencia estándar): incluye ScenarioComparison con las opciones de plazo de la "
                "oferta (`options`), PlanTable y LoanOffer; menciona la siguiente mejor acción con monto "
                "y efecto medido.",
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
            "RAÍZ OBLIGATORIA: exactamente UN componente debe tener \"id\": \"root\"; es el nodo que el "
            "cliente dibuja primero y del que cuelga todo lo demás vía children/child. Sin un componente "
            "\"root\" la interfaz NO se muestra.",
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

    async def _intake_response(
        self,
        *,
        text: str,
        history: Any,
        audience: Any,
        credit_history: Any,
        state: Mapping[str, Any],
        need_amount: bool,
        need_purpose: bool,
        name: str,
    ) -> tuple[str, str | None]:
        """A natural clarifying turn; deterministic question if the model fails."""
        fallback = loans_fallback.intake_response(
            name=name or None, need_amount=need_amount, need_purpose=need_purpose
        )
        try:
            generated = await asyncio.wait_for(
                self._provider.generate(
                    [
                        ChatMessage(role="system", content=self._system_prompt(audience, intake=True)),
                        ChatMessage(
                            role="user",
                            content=(
                                "Estado de la conversación:\n"
                                + json.dumps(dict(state), ensure_ascii=False)
                                + "\n\nDatos del usuario (JSON):\n"
                                + json.dumps(_compact_credit_history(credit_history), ensure_ascii=False)
                                + "\n\nConversación previa:\n"
                                + json.dumps(_recent_history(history), ensure_ascii=False)
                                + f"\n\nMensaje del usuario: {text}"
                                + ("\n\nFalta el MONTO (pídelo)." if need_amount else "")
                                + ("\nFalta el PROPÓSITO (pídelo; si prefiere, puede responder "
                                   "\"es privado\" y no volverás a preguntar)." if need_purpose else "")
                                + "\nPregunta con naturalidad lo que falte y devuelve terminal_response = null."
                            ),
                        ),
                    ],
                    response_schema=LOANS_SCHEMA,
                    max_tokens=300,
                ),
                timeout=self._intake_deadline_seconds,
            )
            parsed = _parse_json(generated.text)
            candidate = str(parsed.get("response_text") or "").strip()
            if candidate:
                return candidate, None
            return fallback, "empty_intake"
        except (ProviderError, asyncio.TimeoutError, TimeoutError) as exc:
            return fallback, f"intake_{type(exc).__name__}"
        except Exception as exc:
            return fallback, f"intake_{type(exc).__name__}"

    async def consult(
        self,
        *,
        user_id: str,
        text: str,
        loan_request_id: str,
        history: list[dict[str, str]] | None = None,
        state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        logger.info("loans_consult_started", user_id=user_id, loan_request_id=loan_request_id)
        started = time.perf_counter()

        # Conversation state keeps the negotiation consistent across turns: the term
        # the user chose, the amount they asked for, and the purpose. Without a
        # persisted amount every later turn would recompute the maximum offer.
        state = dict(state or {})
        requested_term = int(state["requested_term"]) if state.get("requested_term") else None
        confirmed = bool(state.get("term_confirmed"))
        requested_amount = float(state["requested_amount"]) if state.get("requested_amount") else None
        purpose = state.get("purpose") or None
        use_max = bool(state.get("use_max"))
        purpose_asked = bool(state.get("purpose_asked"))
        purpose_private = bool(state.get("purpose_private"))

        new_term = _extract_term(text)
        if new_term:
            requested_term = new_term
            confirmed = False
        elif requested_term and _is_negative(text):
            requested_term = None
            confirmed = False
        elif requested_term and _is_affirmative(text):
            confirmed = True

        amount_in_text = _extract_amount(text)
        if amount_in_text:
            requested_amount = amount_in_text
        if _wants_max(text):
            use_max = True
        purpose_in_text = _extract_purpose(text)
        if purpose_in_text:
            purpose = purpose_in_text
        if _wants_private(text):
            purpose = "privado"
            purpose_private = True

        has_amount = requested_amount is not None or use_max
        state.update(
            {
                "requested_amount": requested_amount,
                "purpose": purpose,
                "purpose_private": purpose_private,
                "use_max": use_max,
                "requested_term": requested_term,
                "term_confirmed": confirmed,
                "purpose_asked": purpose_asked,
            }
        )

        context = await self._toolbox.call("get_credit_history", {"user_id": user_id})
        audience_result = await self._toolbox.call("get_audience", {"user_id": user_id})
        audience = audience_result.get("audience") if isinstance(audience_result, dict) else None
        credit_history = context.get("creditHistory", {}) or {}
        profile = credit_history.get("profile") if isinstance(credit_history, dict) else None
        name = str((profile or {}).get("name") or "").strip().split(" ")[0] if isinstance(profile, Mapping) else ""

        async def _intake(need_amount: bool, need_purpose: bool) -> dict[str, Any]:
            state["purpose_asked"] = True
            response_text, intake_error = await self._intake_response(
                text=text,
                history=history,
                audience=audience,
                credit_history=credit_history,
                state=state,
                need_amount=need_amount,
                need_purpose=need_purpose,
                name=name,
            )
            audio = await self._synthesize(response_text, user_id)
            await self._trace(started, error=intake_error)
            logger.info(
                "loans_intake_turn",
                user_id=user_id,
                loan_request_id=loan_request_id,
                need_amount=need_amount,
                need_purpose=need_purpose,
                used_deterministic=bool(intake_error),
            )
            return {
                "status": "ok",
                "loan_request_id": loan_request_id,
                "response_text": response_text,
                "confidence": 1.0,
                "audio_id": (audio or {}).get("audio_id"),
                "audio_ref": (audio or {}).get("audio_ref"),
                "terminal_response": None,
                "state": state,
            }

        need_purpose = purpose is None and not purpose_asked and not purpose_private

        # Intake: without an amount (and no explicit maximum) we cannot offer yet.
        if not has_amount:
            return await _intake(need_amount=True, need_purpose=need_purpose)

        analysis = await self._toolbox.call("analyze_loans", {"user_id": user_id})
        offer = await self._toolbox.call(
            "compute_loan_offer",
            {
                "user_id": user_id,
                "requested_amount": requested_amount or 0.0,
                "requested_term": requested_term or 0,
            },
        )

        # The user asked for a specific term: never ignore it. Confirm it and
        # explain the real implications before turning it into an offer. If the
        # purpose is still unknown, ask it in the same turn.
        if requested_term and not confirmed:
            propose = offer.get("offer", offer) if isinstance(offer, Mapping) else {}
            response_text = _confirmation_text(propose, requested_term, name or None)
            if need_purpose:
                response_text += (
                    " ¿Y para qué usarías el crédito? Si lo prefieres, puedes decirme que es privado."
                )
                state["purpose_asked"] = True
            audio = await self._synthesize(response_text, user_id)
            await self._trace(started, error=None)
            logger.info(
                "loans_term_confirmation_requested",
                user_id=user_id,
                loan_request_id=loan_request_id,
                requested_term=requested_term,
            )
            return {
                "status": "ok",
                "loan_request_id": loan_request_id,
                "response_text": response_text,
                "confidence": 1.0,
                "audio_id": (audio or {}).get("audio_id"),
                "audio_ref": (audio or {}).get("audio_ref"),
                "terminal_response": None,
                "state": state,
            }

        # Ask once for the purpose before offering.
        if need_purpose:
            return await _intake(need_amount=False, need_purpose=True)

        await self._toolbox.call(
            "store_loan_offer",
            {
                "loan_request_id": loan_request_id,
                "user_id": user_id,
                "offer": offer.get("offer", offer),
            },
        )
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
                    + json.dumps(_trimmed_analysis(analysis), ensure_ascii=False)
                    + "\n\nOFERTA DETERMINISTA (amount, apr, months, monthlyPayment, totalInterest, "
                    "cat y riesgo; úsala tal cual en LoanOffer):\n"
                    + json.dumps(_offer_for_prompt(offer), ensure_ascii=False)
                    + "\n\nEstado de la conversación (monto, propósito y plazo):\n"
                    + json.dumps(
                        {
                            "requested_amount": requested_amount,
                            "purpose": purpose,
                            "use_max": use_max,
                            "requested_term": requested_term,
                            "term_confirmed": confirmed,
                        },
                        ensure_ascii=False,
                    )
                    + "\n\nConversación previa:\n"
                    + json.dumps(_recent_history(history), ensure_ascii=False)
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

        # Deterministic safety net: timeout, provider error, invalid output, or a
        # low-confidence terminal fall back to an engine-built interface. This runs
        # only once an amount is known (intake returned earlier), so the offer is
        # the requested one, never an accidental maximum.
        fallback_reason: str | None = None
        if parsed is None or (terminal is not None and confidence <= CONFIDENCE_THRESHOLD):
            fallback_reason = error or ("low_confidence" if terminal is not None else "invalid_output")
            fallback = loans_fallback.build_terminal(
                profile=profile,
                audience=audience,
                offer=offer,
                analysis=analysis,
                requested_amount=requested_amount,
                use_max=use_max,
            )
            if not response_text:
                response_text = str(fallback.get("response_text") or "")
            if fallback.get("terminal_response") is not None:
                terminal = fallback["terminal_response"]
                confidence = 1.0
            elif parsed is None:
                terminal = None
            logger.info(
                "loans_fallback_used",
                user_id=user_id,
                loan_request_id=loan_request_id,
                reason=fallback_reason,
            )

        if not response_text:
            response_text = "No pude generar la propuesta en este momento. Intenta de nuevo."

        terminal_payload: dict[str, Any] | None = None
        if terminal is not None:
            propose = offer.get("offer", offer) if isinstance(offer, dict) else {}
            terms = propose.get("offer", {}) if isinstance(propose, dict) else {}
            if isinstance(propose, dict):
                self._apply_term_options(terminal, propose.get("options"))
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
        await self._trace(started, error=error)
        logger.info(
            "loans_consult_completed",
            user_id=user_id,
            loan_request_id=loan_request_id,
            confidence=confidence,
            has_terminal_response=terminal_payload is not None,
            fallback_reason=fallback_reason,
        )
        return {
            "status": "ok",
            "loan_request_id": loan_request_id,
            "response_text": response_text,
            "confidence": confidence,
            "audio_id": (audio or {}).get("audio_id"),
            "audio_ref": (audio or {}).get("audio_ref"),
            "terminal_response": terminal_payload,
            "state": state,
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

    @staticmethod
    def _apply_term_options(terminal: dict[str, Any], options: Any) -> None:
        """Force the terminal's comparison cards to the engine's plazo options.

        The model may emit debt-payoff scenarios (or none); the engine's loan-term
        options are the source of truth, so replace them deterministically.
        """
        scenario = loans_fallback.scenario_component(options)
        if scenario is None:
            return
        components = terminal.get("components")
        if not isinstance(components, list):
            return
        existing = next(
            (
                component
                for component in components
                if isinstance(component, dict)
                and component.get("component") == "ScenarioComparison"
            ),
            None,
        )
        if isinstance(existing, dict):
            existing["scenarios"] = scenario["scenarios"]
            existing["highlightIndex"] = scenario["highlightIndex"]
            existing["title"] = scenario["title"]
            return
        root = next(
            (
                component
                for component in components
                if isinstance(component, dict) and isinstance(component.get("children"), list)
            ),
            None,
        )
        if isinstance(root, dict):
            components.append(scenario)
            root["children"].append(scenario["id"])

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
