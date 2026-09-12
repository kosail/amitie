"""In-process MCP servers and the toolbox that exposes them to the agent.

The package is named `mcp_servers` (not `mcp`) so it does not shadow the
installed `mcp` SDK.
"""

from .toolbox import InProcessToolbox, Toolbox, normalize_tool_result

__all__ = ["InProcessToolbox", "Toolbox", "normalize_tool_result"]
