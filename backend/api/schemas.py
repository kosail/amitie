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


class UiResponse(BaseModel):
    status: str
    surface_id: str
    a2ui: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class TraceResponse(BaseModel):
    trace_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)
