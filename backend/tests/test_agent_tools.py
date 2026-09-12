import asyncio
import unittest

from mcp.server import MCPServer

from agent.tools import build_adk_tools
from mcp_servers.toolbox import InProcessToolbox


class AgentToolsTest(unittest.TestCase):
    def test_wraps_mcp_tool_as_adk_tool(self) -> None:
        server = MCPServer("probe")

        @server.tool()
        async def add(a: int, b: int) -> dict:
            """Add two numbers."""
            return {"sum": a + b}

        captured: list[tuple[str, dict]] = []

        async def run() -> None:
            async with InProcessToolbox({"probe": server}) as toolbox:
                tools = await build_adk_tools(
                    toolbox, on_result=lambda name, result: captured.append((name, result))
                )
                self.assertEqual(len(tools), 1)
                tool = tools[0]
                declaration = tool._get_declaration()
                self.assertEqual(declaration.name, "add")
                self.assertEqual(declaration.parameters_json_schema["required"], ["a", "b"])

                result = await tool.run_async(args={"a": 2, "b": 3}, tool_context=None)
                self.assertEqual(result, {"sum": 5})
                self.assertEqual(captured, [("add", {"sum": 5})])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
