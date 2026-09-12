import asyncio
import json
import unittest

from mcp.server import MCPServer

from mcp_servers.toolbox import InProcessToolbox, normalize_tool_result
from providers.base import ToolSpec


class ToolboxTest(unittest.TestCase):
    def test_lists_and_calls_async_tools(self) -> None:
        server = MCPServer("probe")

        @server.tool()
        async def echo(user_id: str, n: int = 1) -> dict:
            """Echo back a dict."""
            return {"user_id": user_id, "n": n}

        @server.tool()
        async def as_json(user_id: str) -> str:
            """Return a JSON string."""
            return json.dumps({"user_id": user_id})

        async def run() -> None:
            async with InProcessToolbox({"probe": server}) as toolbox:
                specs = await toolbox.list_tools()
                self.assertEqual({spec.name for spec in specs}, {"echo", "as_json"})
                self.assertTrue(all(isinstance(spec, ToolSpec) for spec in specs))

                self.assertEqual(await toolbox.call("echo", {"user_id": "u", "n": 2}), {"user_id": "u", "n": 2})
                self.assertEqual(await toolbox.call("as_json", {"user_id": "u"}), {"user_id": "u"})

                with self.assertRaises(KeyError):
                    await toolbox.call("missing", {})

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
