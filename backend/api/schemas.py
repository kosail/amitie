"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionRequest(BaseModel):
    user_id: str = "u_ana"


class SessionResponse(BaseModel):
    session_id: str
    user_id: str


class MessageRequest(BaseModel):
    session_id: str
    text: str | None = None
    audio_b64: str | None = None
    language: str = "es-MX"


class ActionRequest(BaseModel):
    surface_id: str
    name: str
    source_component_id: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    status: str
    surface_id: str | None = None
    a2ui: list[dict[str, Any]] = Field(default_factory=list)
    assistant_text: str = ""
    issues: list[str] = Field(default_factory=list)
    message: str | None = None
    actor: str | None = None
    round: int | None = None
    catalog_id: str | None = None
    audio_ref: str | None = None
    error_code: str | None = None
    retryable: bool = False


class NegotiationRequest(BaseModel):
    user_id: str = "u_ana"
    position: dict[str, Any] = Field(default_factory=dict)


class UiResponse(BaseModel):
    status: str
    surface_id: str
    a2ui: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    catalog_id: str | None = None
    audio_ref: str | None = None


class TraceResponse(BaseModel):
    trace_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)


class ProviderHealth(BaseModel):
    name: str
    provider: str | None = None
    model: str | None = None
    ok: bool | None = None
    latency_ms: int | None = None
    detail: str | None = None
    error: str | None = None


class ProvidersResponse(BaseModel):
    status: str
    providers: list[ProviderHealth] = Field(default_factory=list)


class SttRequest(BaseModel):
    audio_b64: str
    language: str = "es-MX"
    mime: str = "audio/mpeg"
    provider: str = ""


class SttResponse(BaseModel):
    status: str
    text: str = ""
    provider: str | None = None
    language: str = "es-MX"
    error_code: str | None = None
    message: str | None = None


class TtsRequest(BaseModel):
    text: str
    voice_id: str = ""
    speed: float = 1.0
    provider: str = ""


class TtsResponse(BaseModel):
    status: str
    audio_id: str | None = None
    audio_ref: str | None = None
    provider: str | None = None
    mime: str | None = None
    bytes: int | None = None
    cached: bool = False
    error_code: str | None = None
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


class SavingBagCreateRequest(BaseModel):
    user_id: str = "u_ana"
    name: str
    target_amount: float | None = None
    target_date: str | None = None
    session_id: str | None = None


class SavingBagAnswerRequest(BaseModel):
    user_id: str = "u_ana"
    answers: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str | None = None


class SavingBagRefreshRequest(BaseModel):
    user_id: str = "u_ana"
    session_id: str | None = None


class SavingBagResponse(BaseModel):
    status: str
    bag_id: str | None = None
    bag: dict[str, Any] | None = None
    bags: list[dict[str, Any]] = Field(default_factory=list)
    plan: dict[str, Any] | None = None
    surface_id: str | None = None
    a2ui: list[dict[str, Any]] = Field(default_factory=list)
    assistant_text: str = ""
    issues: list[str] = Field(default_factory=list)
    message: str | None = None
    catalog_id: str | None = None
    audio_ref: str | None = None
    error_code: str | None = None
    retryable: bool = False
