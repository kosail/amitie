"""Expose in-process MCP tools to ADK as `BaseTool` subclasses.

ADK remains the orchestrator; every tool call still travels through the MCP
`Toolbox`, so MCP stays the only door to data and actions (INV-014).
"""

from __future__ import annotations

from typing import Any, Callable

from google.adk.tools.base_tool import BaseTool
from google.genai import types

from mcp_servers.toolbox import Toolbox
from providers.base import ToolSpec

ResultCallback = Callable[[str, dict[str, Any]], None]


class McpTool(BaseTool):
    def __init__(
        self,
        spec: ToolSpec,
        toolbox: Toolbox,
        on_result: ResultCallback | None = None,
    ) -> None:
        super().__init__(name=spec.name, description=spec.description)
        self._spec = spec
        self._toolbox = toolbox
        self._on_result = on_result

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self._spec.parameters,
        )

    async def run_async(self, *, args: dict[str, Any], tool_context: Any) -> Any:
        result = await self._toolbox.call(self.name, dict(args or {}))
        if self._on_result is not None:
            self._on_result(self.name, result)
        return result


async def build_adk_tools(toolbox: Toolbox, on_result: ResultCallback | None = None) -> list[BaseTool]:
    specs = await toolbox.list_tools()
    return [McpTool(spec, toolbox, on_result) for spec in specs]
