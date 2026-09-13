import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from config import Settings
from providers.base import LLMResult, Usage


class DummyLLM:
    name = "dummy"
    model = "dummy"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None):
        return LLMResult(
            text="pong",
            tool_calls=(),
            usage=Usage(1, 1, 2),
            provider="dummy",
            model="dummy",
        )


class OpenApiSwaggerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "api.sqlite3")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _app(self):
        settings = Settings(
            database_path=self.db_path,
            enable_debug_endpoints=False,
        )
        return create_app(provider=DummyLLM(), settings=settings)

    def test_root_redirects_to_swagger(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/", follow_redirects=False)
            self.assertEqual(response.status_code, 307)
            self.assertEqual(response.headers.get("location"), "/swagger")

    def test_swagger_ui_endpoint(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/swagger")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers.get("content-type", ""))
            self.assertIn("swagger-ui", response.text.lower())

    def test_swagger_ui_trailing_slash(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/swagger/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers.get("content-type", ""))
            self.assertIn("swagger-ui", response.text.lower())

    def test_api_swagger_endpoint(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/api/swagger")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers.get("content-type", ""))
            self.assertIn("swagger-ui", response.text.lower())

    def test_docs_endpoint(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/docs")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers.get("content-type", ""))
            self.assertIn("swagger-ui", response.text.lower())

    def test_openapi_json_endpoint(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/openapi.json")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("openapi", data)
            self.assertIn("info", data)
            self.assertIn("paths", data)
            self.assertEqual(data["info"]["title"], "La Mesa API")

    def test_openapi_endpoint(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/openapi")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("openapi", data)
            self.assertIn("info", data)
            self.assertIn("paths", data)
            self.assertEqual(data["info"]["title"], "La Mesa API")

    def test_api_openapi_endpoint(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/api/openapi")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("openapi", data)
            self.assertEqual(data["info"]["title"], "La Mesa API")

    def test_api_openapi_json_endpoint(self) -> None:
        with TestClient(self._app()) as client:
            response = client.get("/api/openapi.json")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("openapi", data)
            self.assertEqual(data["info"]["title"], "La Mesa API")
