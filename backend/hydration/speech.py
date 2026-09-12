"""Pure speech-text extraction for accessible surfaces.

A2UI v0.9 has no audio message, so the spoken summary is derived from the
surface's human-readable text and carried in the data model under `/speech`.
"""

from __future__ import annotations

from typing import Any

_TEXT_PROPS = (
    ("Text", "text"),
    ("Heading", "text"),
    ("Badge", "label"),
    ("Button", "label"),
    ("Card", "title"),
    ("TextField", "label"),
    ("GoalJar", "label"),
    ("OfferCard", "headline"),
    ("BreakAlert", None),
)


def _option_labels(component: dict[str, Any]) -> list[str]:
    options = component.get("options")
    if not isinstance(options, list):
        return []
    labels = []
    for option in options:
        if isinstance(option, dict) and isinstance(option.get("label"), str):
            labels.append(option["label"])
    return labels


def speech_text(components: Any) -> str:
    if not isinstance(components, list):
        return ""
    parts: list[str] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        kind = component.get("component")
        for type_name, prop in _TEXT_PROPS:
            if kind != type_name:
                continue
            value = component.get(prop) if prop else None
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        parts.extend(_option_labels(component))
    return ". ".join(parts)


def speech_object(text: str, audio_ref: str = "", provider: str = "") -> dict[str, str]:
    payload = {"text": text}
    if audio_ref:
        payload["audioRef"] = audio_ref
    if provider:
        payload["provider"] = provider
    return payload
