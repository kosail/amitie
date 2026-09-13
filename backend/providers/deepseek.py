"""DeepSeek LLM adapter (fallback), using the OpenAI-compatible HTTP API.

Implemented directly on `httpx2` (no extra SDK) so the fallback stays small and
easy to test with `httpx2.MockTransport` (INV-013).
"""

from __future__ import annotations

import json
from typing import Any

import httpx2

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


def _tool_call_id(call: ToolCall, index: int) -> str:
    return call.id or f"call_{call.name or index}"


def _message_payload(message: ChatMessage) -> dict[str, Any]:
    if message.role == "tool":
        # The tool_call_id must match the id of the assistant tool call. ADK
        # function calls arrive without ids, so both sides derive the same id
        # from the function name.
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id or f"call_{message.name or 'tool'}",
            "content": message.content,
        }
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.role == "assistant" and message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": _tool_call_id(call, index),
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for index, call in enumerate(message.tool_calls)
        ]
    return payload


class DeepSeekLLM:
    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        *,
        thinking: bool = False,
        timeout: float = 30.0,
        client: httpx2.AsyncClient | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("DEEPSEEK_API_KEY is required for the deepseek provider")
        self._api_key = api_key
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._thinking = thinking
        self._client = client or httpx2.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self.model = model

    async def generate(
        self,
        messages: Messages,
        tools: Tools | None = None,
        response_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_message_payload(message) for message in messages],
            "stream": False,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if not self._thinking:
            payload["thinking"] = {"type": "disabled"}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = await self._client.post(self._endpoint, headers=headers, json=payload)
        except httpx2.HTTPError as exc:
            raise ProviderUnavailableError(f"deepseek request failed: {exc!r}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderUnavailableError(
                f"deepseek unavailable ({response.status_code}): {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise ProviderResponseError(
                f"deepseek error ({response.status_code}): {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderResponseError("deepseek returned invalid JSON") from exc
        return self._to_result(data)

    def _to_result(self, data: dict[str, Any]) -> LLMResult:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderResponseError("deepseek response had no choices")
        message = choices[0].get("message") or {}
        tool_calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise ProviderResponseError(
                    f"deepseek tool arguments were not valid JSON: {raw_arguments!r}"
                ) from exc
            tool_calls.append(
                ToolCall(name=function.get("name", ""), arguments=arguments, id=call.get("id"))
            )
        usage_data = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        return LLMResult(
            text=message.get("content") or "",
            tool_calls=tuple(tool_calls),
            usage=usage,
            provider=self.name,
            model=data.get("model", self.model),
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
