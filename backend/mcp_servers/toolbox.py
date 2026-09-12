"""Toolbox: the agent's single seam onto in-process MCP servers.

Opens one in-memory `mcp.Client` per server (no transport) and exposes
`list_tools()` / `call()` in terms of the provider layer's `ToolSpec`. Swapping
to stdio/HTTP later only changes this module (INV-014).
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from typing import Any, Protocol, runtime_checkable

from mcp import Client
from mcp.server import MCPServer

from providers.base import ToolSpec


@runtime_checkable
class Toolbox(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


def normalize_tool_result(result: Any) -> dict[str, Any]:
    """Normalize an MCP CallToolResult into a plain dict.

    Dict-returning tools arrive as JSON `TextContent`; scalar/string returns
    arrive under `structured_content["result"]`. Both shapes are handled.
    """
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        if set(structured.keys()) == {"result"}:
            structured = structured["result"]
        if isinstance(structured, dict):
            return structured
        if isinstance(structured, str):
            try:
                parsed = json.loads(structured)
            except json.JSONDecodeError:
                return {"result": structured}
            return parsed if isinstance(parsed, dict) else {"result": parsed}

    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
            return parsed if isinstance(parsed, dict) else {"result": parsed}
    return {}


class InProcessToolbox:
    def __init__(self, servers: dict[str, MCPServer]) -> None:
        self._servers = servers
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}
        self._owner: dict[str, str] = {}

    async def __aenter__(self) -> "InProcessToolbox":
        for name, server in self._servers.items():
            client = await self._stack.enter_async_context(Client(server))
            self._clients[name] = client
            listed = await client.list_tools()
            for tool in listed.tools:
                self._owner[tool.name] = name
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self._stack.aclose()

    async def list_tools(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for client in self._clients.values():
            listed = await client.list_tools()
            for tool in listed.tools:
                specs.append(
                    ToolSpec(
                        name=tool.name,
                        description=tool.description or "",
                        parameters=tool.input_schema or {"type": "object"},
                    )
                )
        return specs

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        owner = self._owner.get(name)
        if owner is None:
            raise KeyError(f"unknown tool: {name!r}")
        result = await self._clients[owner].call_tool(name, arguments)
        payload = normalize_tool_result(result)
        if getattr(result, "is_error", False):
            payload.setdefault("status", "error")
        return payload
