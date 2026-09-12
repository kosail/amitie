"""Gemini LLM adapter (primary), built on the official `google-genai` SDK."""

from __future__ import annotations

import json
from typing import Any

from .base import (
    ChatMessage,
    LLMResult,
    Messages,
    ProviderResponseError,
    ProviderUnavailableError,
    ToolCall,
    Tools,
    Usage,
)


def _to_contents(messages: Messages) -> list[Any]:
    from google.genai import types

    contents = []
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "tool":
            # Gemini only accepts the roles "user" and "model"; a function
            # response is sent back in a "user" turn (SDK: Content.role).
            try:
                parsed = json.loads(message.content) if message.content else {}
            except (ValueError, TypeError):
                parsed = {"result": message.content}
            response = parsed if isinstance(parsed, dict) else {"result": parsed}
            part = types.Part.from_function_response(
                name=message.name or "tool", response=response
            )
            contents.append(types.Content(role="user", parts=[part]))
        elif message.role == "assistant":
            parts = []
            if message.content:
                parts.append(types.Part.from_text(text=message.content))
            for call in message.tool_calls:
                parts.append(types.Part.from_function_call(name=call.name, args=call.arguments))
            if parts:
                contents.append(types.Content(role="model", parts=parts))
        else:
            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(text=message.content)])
            )
    return contents


def _to_config(
    messages: Messages,
    tools: Tools | None,
    response_schema: dict[str, Any] | None,
    temperature: float | None,
) -> Any:
    from google.genai import types

    kwargs: dict[str, Any] = {}
    system_parts = [m.content for m in messages if m.role == "system" and m.content]
    if system_parts:
        kwargs["system_instruction"] = "\n".join(system_parts)
    if tools:
        kwargs["tools"] = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description,
                        parameters_json_schema=tool.parameters,
                    )
                    for tool in tools
                ]
            )
        ]
    if response_schema is not None:
        kwargs["response_mime_type"] = "application/json"
        kwargs["response_json_schema"] = response_schema
    if temperature is not None:
        kwargs["temperature"] = temperature
    return types.GenerateContentConfig(**kwargs)


def _translate(exc: Exception) -> Exception:
    from google.genai import errors

    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", None)
        if code == 429 or (isinstance(code, int) and code >= 500):
            return ProviderUnavailableError(f"gemini unavailable ({code}): {exc}")
        return ProviderResponseError(f"gemini error ({code}): {exc}")
    return ProviderUnavailableError(f"gemini request failed: {exc!r}")


def _to_result(response: Any, provider: str, model: str) -> LLMResult:
    try:
        text = response.text or ""
    except Exception:
        text = ""
    tool_calls = tuple(
        ToolCall(name=call.name or "", arguments=dict(call.args or {}))
        for call in (response.function_calls or [])
    )
    usage = Usage()
    metadata = getattr(response, "usage_metadata", None)
    if metadata is not None:
        usage = Usage(
            prompt_tokens=metadata.prompt_token_count or 0,
            completion_tokens=metadata.candidates_token_count or 0,
            total_tokens=metadata.total_token_count or 0,
        )
    return LLMResult(
        text=text, tool_calls=tool_calls, usage=usage, provider=provider, model=model
    )


class GeminiLLM:
    name = "gemini"

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        if not api_key and client is None:
            raise ValueError("GEMINI_API_KEY is required for the gemini provider")
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self.model = model

    async def generate(
        self,
        messages: Messages,
        tools: Tools | None = None,
        response_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        config = _to_config(messages, tools, response_schema, temperature)
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=_to_contents(messages), config=config
            )
        except Exception as exc:
            raise _translate(exc) from exc
        return _to_result(response, self.name, self.model)
