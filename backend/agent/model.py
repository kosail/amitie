"""ADK <-> provider-gateway model adapter.

`GatewayLlm` is a custom ADK `BaseLlm` that delegates every model call to the
M2 provider gateway. This keeps ADK as the orchestrator (INV-011) while the
Gemini -> DeepSeek failover stays in the gateway (INV-012).
"""

from __future__ import annotations

import json
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import ConfigDict, PrivateAttr

from providers.base import (
    ChatMessage,
    LLMProvider,
    LLMResult,
    ToolCall,
    ToolSpec,
)
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


class ModelCallLimitError(RuntimeError):
    """Raised when a single agent turn exceeds the model-call budget."""


def _text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = getattr(content, "parts", None) or []
    return "\n".join(part.text for part in parts if getattr(part, "text", None))


def to_messages(llm_request: Any) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    config = getattr(llm_request, "config", None)
    system_instruction = getattr(config, "system_instruction", None) if config else None
    if system_instruction:
        messages.append(ChatMessage(role="system", content=_text_of(system_instruction)))

    for content in getattr(llm_request, "contents", None) or []:
        role = getattr(content, "role", None)
        texts: list[str] = []
        calls: list[ToolCall] = []
        tool_messages: list[ChatMessage] = []
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None):
                texts.append(part.text)
            function_call = getattr(part, "function_call", None)
            if function_call:
                calls.append(
                    ToolCall(
                        name=function_call.name,
                        arguments=dict(function_call.args or {}),
                        thought_signature=getattr(part, "thought_signature", None),
                    )
                )
            function_response = getattr(part, "function_response", None)
            if function_response:
                tool_messages.append(
                    ChatMessage(
                        role="tool",
                        name=function_response.name,
                        content=json.dumps(function_response.response or {}),
                    )
                )
        if tool_messages:
            messages.extend(tool_messages)
        elif calls:
            messages.append(
                ChatMessage(role="assistant", content="\n".join(texts), tool_calls=tuple(calls))
            )
        else:
            messages.append(
                ChatMessage(
                    role="assistant" if role == "model" else "user", content="\n".join(texts)
                )
            )
    return messages


def to_tool_specs(llm_request: Any) -> list[ToolSpec]:
    config = getattr(llm_request, "config", None)
    specs: list[ToolSpec] = []
    for tool in getattr(config, "tools", None) or []:
        for declaration in getattr(tool, "function_declarations", None) or []:
            specs.append(
                ToolSpec(
                    name=declaration.name,
                    description=declaration.description or "",
                    parameters=getattr(declaration, "parameters_json_schema", None) or _DEFAULT_SCHEMA,
                )
            )
    return specs


def to_llm_response(result: LLMResult) -> LlmResponse:
    parts: list[Any] = []
    for call in result.tool_calls:
        part = types.Part.from_function_call(name=call.name, args=call.arguments)
        if call.thought_signature:
            part.thought_signature = call.thought_signature
        parts.append(part)
    if result.text:
        parts.append(types.Part.from_text(text=result.text))
    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=result.usage.prompt_tokens or None,
        candidates_token_count=result.usage.completion_tokens or None,
        total_token_count=result.usage.total_tokens or None,
    )
    return LlmResponse(
        content=types.Content(role="model", parts=parts),
        usage_metadata=usage,
        turn_complete=not result.tool_calls,
    )


class GatewayLlm(BaseLlm):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: LLMProvider
    max_calls: int = 10
    _calls: int = PrivateAttr(default=0)

    @classmethod
    def supported_models(cls) -> list[str]:
        return ["gateway"]

    def reset_calls(self) -> None:
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def limit(self) -> int:
        return self.max_calls

    async def generate_content_async(self, llm_request: Any, stream: bool = False):
        self._calls += 1
        if self._calls > self.max_calls:
            raise ModelCallLimitError(f"exceeded max model calls ({self.max_calls})")
        messages = to_messages(llm_request)
        tools = to_tool_specs(llm_request)
        result = await self.provider.generate(messages, tools=tools or None)
        logger.info(
            "agent_model_call",
            index=self._calls,
            max_calls=self.max_calls,
            tool_calls=[call.name for call in result.tool_calls],
        )
        yield to_llm_response(result)
