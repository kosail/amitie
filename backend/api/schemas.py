"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HttpErrorDetail(BaseModel):
    """Standard HTTP error response payload."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"detail": "unknown session"}]}
    )

    detail: str = Field(
        description="Human-readable explanation of why the request failed.",
        examples=["unknown session"],
    )


class SessionRequest(BaseModel):
    """Payload to initialize a new conversation session."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"user_id": "u_ana"}]}
    )

    user_id: str = Field(
        default="u_ana",
        description="User identifier to bind this session to (e.g. seeded demo user 'u_ana').",
        examples=["u_ana"],
    )


class SessionResponse(BaseModel):
    """Response returned upon session creation."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"session_id": "sess_1a2b3c4d5e6f", "user_id": "u_ana"}]
        }
    )

    session_id: str = Field(
        description="Unique session identifier for following agent turns.",
        examples=["sess_1a2b3c4d5e6f"],
    )
    user_id: str = Field(
        description="User identifier associated with the session.",
        examples=["u_ana"],
    )


class MessageRequest(BaseModel):
    """Payload containing the user's natural language or voice utterance."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "session_id": "sess_demo",
                    "text": "Tengo cinco deudas y no me alcanza el mes",
                    "language": "es-MX",
                }
            ]
        }
    )

    session_id: str = Field(
        description="Active conversation session ID.",
        examples=["sess_demo"],
    )
    text: str | None = Field(
        default=None,
        description="User message in natural language. Required if audio_b64 is omitted.",
        examples=["Tengo cinco deudas y no me alcanza el mes"],
    )
    audio_b64: str | None = Field(
        default=None,
        description="Base64-encoded audio. Transcribed via voice MCP when text is absent (REQ-ACC-04).",
    )
    language: str = Field(
        default="es-MX",
        description="BCP-47 language tag for audio transcription.",
        examples=["es-MX"],
    )


class ActionRequest(BaseModel):
    """Closed-loop action payload emitted from an A2UI component."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "surface_id": "surf_abc123",
                    "name": "tune_tradeoff",
                    "source_component_id": "tradeoff_slider",
                    "context": {"liquidity_weight": 0.8},
                }
            ]
        }
    )

    surface_id: str = Field(
        description="ID of the generated UI surface where the action originated.",
        examples=["surf_abc123"],
    )
    name: str = Field(
        description="A2UI action name, e.g. tune_tradeoff, toggle_assumption, accept_offer (INV-017).",
        examples=["tune_tradeoff"],
    )
    source_component_id: str = Field(
        default="",
        description="ID of the A2UI component that dispatched the action.",
        examples=["tradeoff_slider"],
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary action context parameters provided by the component.",
        examples=[{"liquidity_weight": 0.8}],
    )


class AgentResponse(BaseModel):
    """Standard agent turn response carrying the generated A2UI interface and metadata."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "surface_id": "surf_1a2b3c4d",
                    "a2ui": [
                        {
                            "type": "beginRendering",
                            "catalogId": "amitie.standard.v1",
                            "surfaceId": "surf_1a2b3c4d",
                            "root": "root",
                        }
                    ],
                    "assistant_text": "He analizado tus deudas y reestructurado el plan.",
                    "issues": [],
                    "catalog_id": "amitie.standard.v1",
                    "audio_ref": "/api/audio/asset_123",
                    "retryable": False,
                }
            ]
        }
    )

    status: str = Field(
        description="Execution status ('ok' or 'error').",
        examples=["ok"],
    )
    surface_id: str | None = Field(
        default=None,
        description="Identifier of the active or newly persisted A2UI surface.",
        examples=["surf_1a2b3c4d"],
    )
    a2ui: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Full A2UI message array for this turn (INV-010, INV-016).",
    )
    assistant_text: str = Field(
        default="",
        description="Text utterance or commentary from the AI agent.",
        examples=["He analizado tus deudas y reestructurado el plan."],
    )
    issues: list[str] = Field(
        default_factory=list,
        description="List of warnings, schema validation issues, or soft errors.",
    )
    message: str | None = Field(
        default=None,
        description="Optional human-readable error or status message.",
    )
    actor: str | None = Field(
        default=None,
        description="Current acting party in negotiation ('user' or 'bank').",
        examples=["bank"],
    )
    round: int | None = Field(
        default=None,
        description="Current negotiation round index.",
        examples=[1],
    )
    catalog_id: str | None = Field(
        default=None,
        description="Catalog ID used to render the interface ('amitie.standard.v1' or 'amitie.voz_color.v1').",
        examples=["amitie.standard.v1"],
    )
    audio_ref: str | None = Field(
        default=None,
        description="URL to stream generated TTS audio for voice accessibility (REQ-ACC-03).",
        examples=["/api/audio/asset_123"],
    )
    error_code: str | None = Field(
        default=None,
        description="Structured error code (e.g. 'provider_unavailable', 'bad_request').",
    )
    retryable: bool = Field(
        default=False,
        description="Indicates whether the client may retry this turn (REQ-NFR-04).",
    )


class NegotiationRequest(BaseModel):
    """Payload to advance or intervene in the El Revés negotiation loop."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "u_ana",
                    "position": {
                        "proposed_rate": 0.22,
                        "proposed_term_months": 36,
                        "proposed_payment": 2800.0,
                    },
                }
            ]
        }
    )

    user_id: str = Field(
        default="u_ana",
        description="User identifier negotiating terms.",
        examples=["u_ana"],
    )
    position: dict[str, Any] = Field(
        default_factory=dict,
        description="User-proposed terms or counteroffer parameters.",
    )


class UiResponse(BaseModel):
    """Response containing a freshly hydrated A2UI surface."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "surface_id": "surf_1a2b3c4d",
                    "a2ui": [],
                    "issues": [],
                    "catalog_id": "amitie.standard.v1",
                }
            ]
        }
    )

    status: str = Field(
        description="Status of the hydration request ('ok' or 'error').",
        examples=["ok"],
    )
    surface_id: str = Field(
        description="Surface identifier.",
        examples=["surf_1a2b3c4d"],
    )
    a2ui: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Freshly hydrated A2UI message array (INV-022).",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Hydration or revalidation issues, if any.",
    )
    catalog_id: str | None = Field(
        default=None,
        description="Catalog identifier for rendering.",
        examples=["amitie.standard.v1"],
    )
    audio_ref: str | None = Field(
        default=None,
        description="Optional audio asset reference.",
    )


class TraceResponse(BaseModel):
    """Chronological execution trace for a single request (INV-018, REQ-NFR-02)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "trace_id": "tr_1a2b3c4d",
                    "events": [
                        {
                            "timestamp": "2026-09-12T10:00:00Z",
                            "kind": "llm_call",
                            "provider": "gemini",
                            "model": "gemini-2.5-flash",
                            "latency_ms": 450,
                        }
                    ],
                }
            ]
        }
    )

    trace_id: str = Field(
        description="Unique trace identifier.",
        examples=["tr_1a2b3c4d"],
    )
    events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Array of structured trace event objects.",
    )


class SavingBagCreateRequest(BaseModel):
    """Payload to initiate a new Saving Bag goal."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "u_ana",
                    "name": "Viaje a Japón",
                    "target_amount": 75000.0,
                    "target_date": "2027-04-15",
                    "session_id": "sess_demo",
                }
            ]
        }
    )

    user_id: str = Field(
        default="u_ana",
        description="Owner user identifier.",
        examples=["u_ana"],
    )
    name: str = Field(
        description="Name of the savings goal (e.g. 'Viaje a Japón').",
        examples=["Viaje a Japón"],
    )
    target_amount: float | None = Field(
        default=None,
        description="User-estimated target cost in MXN.",
        examples=[75000.0],
    )
    target_date: str | None = Field(
        default=None,
        description="Target completion date in ISO format (YYYY-MM-DD).",
        examples=["2027-04-15"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional active session to bind generated UI to.",
        examples=["sess_demo"],
    )


class SavingBagAnswerRequest(BaseModel):
    """Answers submitted for clarification questions about a saving bag."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "u_ana",
                    "answers": [
                        {"question_id": "duration_days", "value": 14},
                        {"question_id": "travelers", "value": 2},
                        {"question_id": "season", "value": "cherry_blossom"},
                    ],
                }
            ]
        }
    )

    user_id: str = Field(
        default="u_ana",
        description="Owner user identifier.",
        examples=["u_ana"],
    )
    answers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Key-value answers matching the agent's generated clarification questions.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session to bind the updated UI to.",
    )


class SavingBagRefreshRequest(BaseModel):
    """Request to refresh real cost research and feasibility calculation."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"user_id": "u_ana"}]}
    )

    user_id: str = Field(
        default="u_ana",
        description="Owner user identifier.",
        examples=["u_ana"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session identifier.",
    )


class SavingBagResponse(BaseModel):
    """Composite response for Saving Bags operations including metadata and A2UI plan."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "bag_id": "bag_123",
                    "bag": {"id": "bag_123", "name": "Viaje a Japón", "target_amount": 75000.0},
                    "bags": [],
                    "plan": {"monthly_saving": 4500.0, "months": 16, "feasible": True},
                    "surface_id": "surf_bag123",
                    "a2ui": [],
                    "assistant_text": "He investigado los costos reales y calculado tu plan de ahorro.",
                    "issues": [],
                }
            ]
        }
    )

    status: str = Field(
        description="Status ('ok' or 'error').",
        examples=["ok"],
    )
    bag_id: str | None = Field(
        default=None,
        description="Saving bag identifier.",
        examples=["bag_123"],
    )
    bag: dict[str, Any] | None = Field(
        default=None,
        description="Saving bag entity attributes.",
    )
    bags: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of saving bags (populated when listing bags).",
    )
    plan: dict[str, Any] | None = Field(
        default=None,
        description="Calculated financial feasibility plan (INV-015).",
    )
    surface_id: str | None = Field(
        default=None,
        description="Active A2UI surface ID for the saving bag.",
    )
    a2ui: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Full A2UI message array for rendering.",
    )
    assistant_text: str = Field(
        default="",
        description="Agent commentary and explanation.",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Issues or warnings encountered.",
    )
    message: str | None = Field(
        default=None,
        description="Human-readable status or error message.",
    )
    catalog_id: str | None = Field(
        default=None,
        description="A2UI catalog identifier.",
    )
    audio_ref: str | None = Field(
        default=None,
        description="Audio stream reference URL.",
    )
    error_code: str | None = Field(
        default=None,
        description="Structured error code.",
    )
    retryable: bool = Field(
        default=False,
        description="Whether this operation is retryable.",
    )
