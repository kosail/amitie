"""Deterministic audience/comprehension classification (INV-015).

Decides how simple or detailed a generated interface must be for a specific user,
from real data: age, accessibility flags, last obtained degree (comprehension),
and actual financial activity (transaction volume, distinct categories,
accounts/liabilities/subscriptions => financial sophistication). The LLM only
follows the resulting directive; it never decides the audience.
"""

from __future__ import annotations

from typing import Any, Mapping

_BASIC_EDUCATION = {"ninguna", "primaria", "secundaria", "basica", "básica"}
_ADVANCED_EDUCATION = {
    "preparatoria",
    "bachillerato",
    "licenciatura",
    "ingenieria",
    "ingeniería",
    "maestria",
    "maestría",
    "posgrado",
    "doctorado",
}
_SIMPLE_MODES = {"low_literacy", "blind", "elderly", "special", "special_needs", "other"}

_LEVEL_MAX_SECTIONS = {"simple": 2, "standard": 4, "detailed": 6}

_DIRECTIVES = {
    "simple": (
        "AUDIENCIA: comprensión BÁSICA (edad avanzada, baja alfabetización o educación básica). "
        "Usa frases cortas y lenguaje llano; UNA idea por sección; sin tecnicismos (explica la tasa y "
        "el CAT en palabras simples); números grandes; sin tablas densas; máximo 2 secciones. "
        "SIEMPRE incluye LoanOffer con el monto y el pago mensual."
    ),
    "standard": (
        "AUDIENCIA: comprensión INTERMEDIA. Equilibra claridad y detalle: un resumen, el calendario "
        "de pagos y una comparación de escenarios; explica los términos clave en una línea."
    ),
    "detailed": (
        "AUDIENCIA: comprensión AVANZADA y alta actividad financiera. Incluye CAT, DTI, panel de "
        "riesgo, calendario completo, gráficas y comparación de escenarios; puedes ser técnico."
    ),
}


def _comprehension(profile: Mapping[str, Any], accessibility_mode: Any) -> str:
    age = int(profile.get("age") or 0)
    education = str(profile.get("educationLevel") or "").strip().lower()
    mode = str(accessibility_mode or "").strip().lower()
    if age >= 65 or mode in _SIMPLE_MODES or education in _BASIC_EDUCATION:
        return "basic"
    if education in _ADVANCED_EDUCATION:
        return "advanced"
    return "intermediate"


def _sophistication(
    transaction_count: int,
    distinct_categories: int,
    account_count: int,
    liability_count: int,
    subscription_count: int,
) -> str:
    if transaction_count >= 40 or distinct_categories >= 6 or liability_count >= 4:
        return "high"
    if transaction_count <= 8 and liability_count <= 1 and account_count <= 1:
        return "low"
    return "medium"


def classify(
    profile: Mapping[str, Any],
    *,
    accessibility_mode: Any = None,
    transaction_count: int = 0,
    distinct_categories: int = 0,
    account_count: int = 0,
    liability_count: int = 0,
    subscription_count: int = 0,
) -> dict[str, Any]:
    comprehension = _comprehension(profile, accessibility_mode)
    sophistication = _sophistication(
        int(transaction_count or 0),
        int(distinct_categories or 0),
        int(account_count or 0),
        int(liability_count or 0),
        int(subscription_count or 0),
    )
    if comprehension == "basic":
        level = "simple"
    elif comprehension == "advanced" and sophistication != "low":
        level = "detailed"
    else:
        level = "standard"
    return {
        "level": level,
        "comprehension": comprehension,
        "financialSophistication": sophistication,
        "explainTerms": level == "simple",
        "showAdvancedMetrics": level == "detailed",
        "showCharts": level != "simple",
        "maxSections": _LEVEL_MAX_SECTIONS[level],
        "directive": _DIRECTIVES[level],
        "signals": {
            "age": profile.get("age"),
            "educationLevel": profile.get("educationLevel"),
            "accessibilityMode": accessibility_mode,
            "transactions": int(transaction_count or 0),
            "distinctCategories": int(distinct_categories or 0),
            "liabilities": int(liability_count or 0),
            "accounts": int(account_count or 0),
        },
    }
