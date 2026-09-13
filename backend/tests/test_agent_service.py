import asyncio
import tempfile
import unittest
from pathlib import Path

from agent.service import AgentService
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.finance.server import build_finance_server
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from providers.base import LLMResult, ProviderUnavailableError, ToolCall, Usage
from ui_contract.validator import CatalogValidator

CATALOG_ID = "amitie.standard.v1"

COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["title"], "gap": 8},
    {"id": "title", "component": "Heading", "text": "Deuda total: {{totals.debt}}"},
]


def tool_call(name: str, arguments: dict) -> LLMResult:
    return LLMResult(
        text="",
        tool_calls=(ToolCall(name=name, arguments=arguments),),
        usage=Usage(1, 1, 2),
        provider="scripted",
        model="scripted",
    )


def text_result(text: str) -> LLMResult:
    return LLMResult(
        text=text, tool_calls=(), usage=Usage(1, 1, 2), provider="scripted", model="scripted"
    )


class ScriptedProvider:
    name = "scripted"
    model = "scripted"

    def __init__(self, results: list[LLMResult]) -> None:
        self._results = list(results)
        self.calls: list[list] = []

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        self.calls.append(list(messages))
        if not self._results:
            return text_result("(sin guion)")
        return self._results.pop(0)


class FailingProvider:
    name = "failing"
    model = "failing"

    async def generate(self, *args, **kwargs):
        raise ProviderUnavailableError("provider down")


class LoopingProvider:
    """Always asks for another tool call, so a turn never reaches persist_ui."""

    name = "looping"
    model = "looping"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        return tool_call("get_financial_context", {"user_id": "u_ana"})


def _persist_call() -> LLMResult:
    return tool_call(
        "persist_ui",
        {
            "user_id": "u_ana",
            "domain": "loans_credits",
            "catalog_id": CATALOG_ID,
            "components": COMPONENTS,
            "data_model": {},
        },
    )


class AgentServiceTest(unittest.TestCase):
    def _make_toolbox(self, database):
        servers = {"finance": build_finance_server(database), "ui": build_ui_server(database)}
        return InProcessToolbox(servers)

    def test_turn_persists_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "agent.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with self._make_toolbox(database) as toolbox:
                    provider = ScriptedProvider(
                        [
                            tool_call("get_financial_context", {"user_id": "u_ana"}),
                            _persist_call(),
                            text_result("Listo, aquí está tu diagnóstico."),
                        ]
                    )
                    service = AgentService(provider=provider, toolbox=toolbox)
                    result = await service.run_turn(
                        session_id="s1", user_id="u_ana", text="Tengo 5 deudas y ya no puedo"
                    )

                    self.assertEqual(result["status"], "ok")
                    self.assertTrue(result["surface_id"].startswith("surf_"))
                    self.assertEqual(result["assistant_text"], "Listo, aquí está tu diagnóstico.")
                    self.assertTrue(CatalogValidator().validate(result["a2ui"]).ok, result["a2ui"])

                    row = await database.fetch_one(
                        "SELECT id FROM generated_ui WHERE id = ?", (result["surface_id"],)
                    )
                    self.assertIsNotNone(row)

                await database.close()

            asyncio.run(run())

    def test_provider_failure_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "agent.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with self._make_toolbox(database) as toolbox:
                    service = AgentService(provider=FailingProvider(), toolbox=toolbox)
                    result = await service.run_turn(session_id="s1", user_id="u_ana", text="hola")
                    self.assertEqual(result["status"], "error")
                    self.assertIn("message", result)

                await database.close()

            asyncio.run(run())

    def test_model_call_limit_returns_retryable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "agent.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with self._make_toolbox(database) as toolbox:
                    service = AgentService(
                        provider=LoopingProvider(), toolbox=toolbox, max_model_calls=3
                    )
                    result = await service.run_turn(session_id="s1", user_id="u_ana", text="deudas")
                    self.assertEqual(result["status"], "error")
                    self.assertEqual(result["error_code"], "model_call_limit")
                    self.assertTrue(result["retryable"])
                    self.assertIn("message", result)

                await database.close()

            asyncio.run(run())

    def test_agent_call_budget_default(self) -> None:
        from config import Settings

        self.assertGreaterEqual(Settings().agent_max_model_calls, 12)

    def test_missing_persist_ui_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "agent.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with self._make_toolbox(database) as toolbox:
                    provider = ScriptedProvider([text_result("solo texto")])
                    service = AgentService(provider=provider, toolbox=toolbox)
                    result = await service.run_turn(session_id="s1", user_id="u_ana", text="hola")
                    self.assertEqual(result["status"], "error")
                    self.assertIn("persist_ui", result["issues"][0])

                await database.close()

            asyncio.run(run())

    def test_session_persists_across_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "agent.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with self._make_toolbox(database) as toolbox:
                    provider = ScriptedProvider(
                        [
                            tool_call("get_financial_context", {"user_id": "u_ana"}),
                            _persist_call(),
                            text_result("turno 1"),
                            text_result("turno 2"),
                        ]
                    )
                    service = AgentService(provider=provider, toolbox=toolbox)
                    first = await service.run_turn(session_id="s1", user_id="u_ana", text="deudas")
                    self.assertEqual(first["status"], "ok")

                    second = await service.run_turn(
                        session_id="s1",
                        user_id="u_ana",
                        action={"name": "tune_tradeoff", "surface_id": first["surface_id"], "context": {"value": 60}},
                    )
                    self.assertEqual(second["status"], "error")  # no persist_ui in turn 2

                    # The turn-2 model call must have seen turn-1 history from the ADK session.
                    turn2_messages = provider.calls[3]
                    self.assertTrue(any(message.tool_calls for message in turn2_messages))

                    session = await service._runner.session_service.get_session(
                        app_name="lamina", user_id="u_ana", session_id="s1"
                    )
                    self.assertIsNotNone(session)
                    self.assertTrue(session.events)

                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()


class _VoiceToolbox:
    async def call(self, name, arguments=None):
        if name == "synthesize_speech":
            return {"status": "ok", "audio_ref": "/api/audio/aud_test", "provider": "fake"}
        return {"status": "ok"}


class SpeechEnricherTest(unittest.TestCase):
    def test_standard_surface_speaks_fallback_text(self) -> None:
        from agent.speech import SpeechEnricher

        enricher = SpeechEnricher(_VoiceToolbox())
        result = {
            "surface_id": "s1",
            "catalog_id": CATALOG_ID,
            "accessible": False,
            "speech": "",
            "a2ui": [{"updateDataModel": {"surfaceId": "s1", "path": "/", "value": {}}}],
        }
        out = asyncio.run(enricher.enrich(result, user_id="u_ana", fallback_text="Hola Ana"))

        self.assertEqual(out["audio_ref"], "/api/audio/aud_test")
        payload = out["a2ui"][0]["updateDataModel"]["value"]["speech"]
        self.assertEqual(payload["text"], "Hola Ana")

    def test_accessible_surface_prefers_spoken_summary(self) -> None:
        from agent.speech import SpeechEnricher

        enricher = SpeechEnricher(_VoiceToolbox())
        result = {
            "surface_id": "s2",
            "catalog_id": CATALOG_ID,
            "accessible": True,
            "speech": "resumen simple",
            "a2ui": [{"updateDataModel": {"surfaceId": "s2", "path": "/", "value": {}}}],
        }
        out = asyncio.run(enricher.enrich(result, user_id="u_don", fallback_text="respuesta larga"))

        payload = out["a2ui"][0]["updateDataModel"]["value"]["speech"]
        self.assertEqual(payload["text"], "resumen simple")
