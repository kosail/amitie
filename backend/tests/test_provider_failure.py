"""Provider failure must surface a clear, retryable error — never a stale surface.

This backs the destructive on-stage test: after a successful generation, deleting
the API key must visibly fail so the real-time nature of the system is provable.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agent.service import AgentService
from api.app import create_app
from config import Settings
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from providers.base import LLMResult, ProviderUnavailableError, ToolCall, Usage

SURFACE = [
    {"id": "root", "component": "Column", "children": ["t"], "gap": 12},
    {"id": "t", "component": "Heading", "text": "Tu plan"},
]


class FailingProvider:
    name = "failing"
    model = "failing"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        raise ProviderUnavailableError("provider down")


class TextOnlyProvider:
    name = "textonly"
    model = "textonly"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        return LLMResult(
            text="solo texto", tool_calls=(), usage=Usage(1, 1, 2), provider="textonly", model="textonly"
        )


def _tool_call(name, arguments):
    return LLMResult(
        text="", tool_calls=(ToolCall(name=name, arguments=arguments),), usage=Usage(1, 1, 2), provider="q", model="q"
    )


def _text(text):
    return LLMResult(text=text, tool_calls=(), usage=Usage(1, 1, 2), provider="q", model="q")


class SwitchProvider:
    name = "switch"
    model = "switch"

    def __init__(self):
        self.fail = False
        self._queue = []

    def push(self, *results):
        self._queue.extend(results)

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        if self.fail:
            raise ProviderUnavailableError("key deleted")
        if self._queue:
            return self._queue.pop(0)
        return _text("(sin guion)")


class AgentFailureTest(unittest.TestCase):
    def test_provider_error_is_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "fail.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                toolbox = InProcessToolbox(
                    {"finance": build_finance_server(database), "ui": build_ui_server(database)}
                )
                await toolbox.__aenter__()
                try:
                    service = AgentService(provider=FailingProvider(), toolbox=toolbox)
                    result = await service.run_turn(session_id="s", user_id="u_ana", text="hola")
                    self.assertEqual(result["status"], "error")
                    self.assertEqual(result["error_code"], "provider_unavailable")
                    self.assertTrue(result["retryable"])
                    self.assertNotIn("a2ui", result)

                    textonly = AgentService(provider=TextOnlyProvider(), toolbox=toolbox)
                    no_ui = await textonly.run_turn(session_id="s2", user_id="u_ana", text="hola")
                    self.assertEqual(no_ui["error_code"], "agent_error")
                    self.assertTrue(no_ui["retryable"])
                finally:
                    await toolbox.__aexit__(None, None, None)
                await database.close()

            asyncio.run(run())


class ApiFailureTest(unittest.TestCase):
    def test_failure_returns_error_not_stale_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "api_fail.sqlite3")

            async def prep() -> None:
                database = LocalSQLiteDatabase(db_path)
                await apply_schema(database)
                await seed(database)
                await database.close()

            asyncio.run(prep())

            provider = SwitchProvider()
            app = create_app(provider=provider, settings=Settings(database_path=db_path))

            with TestClient(app) as client:
                session_id = client.post("/api/session", json={"user_id": "u_ana"}).json()[
                    "session_id"
                ]

                provider.push(
                    _tool_call(
                        "persist_ui",
                        {
                            "user_id": "u_ana",
                            "domain": "loans_credits",
                            "catalog_id": "amitie.standard.v1",
                            "components": SURFACE,
                            "data_model": {},
                        },
                    ),
                    _text("Aquí está."),
                )
                ok = client.post(
                    "/api/message", json={"session_id": session_id, "text": "tengo deudas"}
                ).json()
                self.assertEqual(ok["status"], "ok", ok)
                self.assertTrue(ok["a2ui"])

                # "Delete the key": generation now fails.
                provider.fail = True
                failed = client.post(
                    "/api/message", json={"session_id": session_id, "text": "otra vez"}
                )
                self.assertEqual(failed.status_code, 200)
                body = failed.json()
                self.assertEqual(body["status"], "error", body)
                self.assertEqual(body["error_code"], "provider_unavailable")
                self.assertTrue(body["retryable"])
                self.assertEqual(body["a2ui"], [])
                self.assertIsNone(body["surface_id"])


if __name__ == "__main__":
    unittest.main()
