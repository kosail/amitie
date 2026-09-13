"""Provider interfaces (INV-012).

Normalized, SDK-agnostic types so the orchestrator never depends on a specific
vendor. Switching providers is an `.env` change (INV-013).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str | None = None
    thought_signature: bytes | None = None


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class LLMResult:
    text: str
    tool_calls: tuple[ToolCall, ...]
    usage: Usage
    provider: str
    model: str


class ProviderError(RuntimeError):
    """Base class for provider failures."""


class ProviderUnavailableError(ProviderError):
    """Quota, rate limit, timeout, or network failure. Triggers failover (INV-012)."""


class ProviderResponseError(ProviderError):
    """The provider responded, but the payload was unusable."""


Messages = Sequence[ChatMessage]
Tools = Sequence[ToolSpec]


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def generate(
        self,
        messages: Messages,
        tools: Tools | None = None,
        response_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult: ...
