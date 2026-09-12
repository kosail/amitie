import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from config import Settings
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from providers.base import LLMResult, ToolCall, Usage
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


def persist_call() -> LLMResult:
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


class ScriptedProvider:
    name = "scripted"
    model = "scripted"

    def __init__(self, results: list[LLMResult]) -> None:
        self._results = list(results)

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        if not self._results:
            return text_result("(sin guion)")
        return self._results.pop(0)


def _seed(path: str) -> None:
    async def run() -> None:
        database = LocalSQLiteDatabase(path)
        await apply_schema(database)
        await seed(database)
        await database.close()

    asyncio.run(run())


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "api.sqlite3")
        _seed(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _app(self):
        provider = ScriptedProvider(
            [
                tool_call("get_financial_context", {"user_id": "u_ana"}),
                persist_call(),
                text_result("Aquí está tu diagnóstico."),
                persist_call(),
                text_result("Plan actualizado."),
            ]
        )
        return create_app(provider=provider, settings=Settings(database_path=self.db_path))

    def test_full_loop(self) -> None:
        with TestClient(self._app()) as client:
            session = client.post("/api/session", json={"user_id": "u_ana"})
            self.assertEqual(session.status_code, 200)
            session_id = session.json()["session_id"]

            message = client.post(
                "/api/message", json={"session_id": session_id, "text": "Tengo 5 deudas"}
            )
            self.assertEqual(message.status_code, 200)
            body = message.json()
            self.assertEqual(body["status"], "ok")
            self.assertTrue(body["surface_id"].startswith("surf_"))
            self.assertEqual(body["assistant_text"], "Aquí está tu diagnóstico.")
            self.assertTrue(CatalogValidator().validate(body["a2ui"]).ok, body["a2ui"])
            self.assertIn("x-trace-id", message.headers)

            surface_id = body["surface_id"]
            hydrated = client.get(f"/api/ui/{surface_id}")
            self.assertEqual(hydrated.status_code, 200)
            self.assertTrue(hydrated.json()["a2ui"])

            action = client.post(
                "/api/action",
                json={
                    "surface_id": surface_id,
                    "name": "tune_tradeoff",
                    "source_component_id": "strategy",
                    "context": {"value": 60},
                },
            )
            self.assertEqual(action.status_code, 200)
            self.assertEqual(action.json()["status"], "ok")
            self.assertTrue(action.json()["a2ui"])

            trace = client.get(f"/debug/trace/{message.headers['x-trace-id']}")
            self.assertEqual(trace.status_code, 200)
            self.assertTrue(trace.json()["events"])

            missing = client.post(
                "/api/message", json={"session_id": "nope", "text": "hola"}
            )
            self.assertEqual(missing.status_code, 404)

            unknown_ui = client.get("/api/ui/nope")
            self.assertEqual(unknown_ui.status_code, 404)

    def test_healthz(self) -> None:
        with TestClient(self._app()) as client:
            self.assertEqual(client.get("/healthz").json(), {"status": "ok"})

    def test_app_starts_without_llm_keys(self) -> None:
        app = create_app(settings=Settings(database_path=self.db_path))
        with TestClient(app) as client:
            self.assertEqual(client.get("/healthz").json(), {"status": "ok"})
            self.assertEqual(client.get("/openapi.json").status_code, 200)

    def test_openapi_frozen_contract(self) -> None:
        from api.openapi import FROZEN_OPENAPI_PATHS

        with TestClient(self._app()) as client:
            landing = client.get("/")
            self.assertEqual(landing.status_code, 200)
            self.assertEqual(landing.json()["openapi"], "/openapi.json")

            docs = client.get("/docs")
            self.assertEqual(docs.status_code, 200)
            self.assertIn("text/html", docs.headers.get("content-type", ""))

            swagger = client.get("/swagger")
            self.assertEqual(swagger.status_code, 200)
            self.assertIn("text/html", swagger.headers.get("content-type", ""))

            spec = client.get("/openapi.json")
            self.assertEqual(spec.status_code, 200)
            body = spec.json()
            self.assertEqual(body["info"]["title"], "La Mesa API")
            paths = body["paths"]
            for path in FROZEN_OPENAPI_PATHS:
                self.assertIn(path, paths, path)

    def test_openapi_exporter(self) -> None:
        import json
        from api.openapi import export_openapi, generate_openapi_spec, FROZEN_OPENAPI_PATHS

        spec = generate_openapi_spec()
        self.assertEqual(spec["info"]["title"], "La Mesa API")
        for path in FROZEN_OPENAPI_PATHS:
            self.assertIn(path, spec["paths"], path)

        out_file = Path(self._tmp.name) / "exported_openapi.json"
        rendered = export_openapi(output_path=out_file)
        self.assertTrue(out_file.is_file())
        parsed = json.loads(rendered)
        self.assertEqual(parsed["info"]["title"], "La Mesa API")


if __name__ == "__main__":
    unittest.main()
