import io
import json
import logging
import unittest

import structlog
from fastapi.testclient import TestClient

from api.app import create_app
from config import Settings
from observability.logging_config import configure_logging
from observability.context import trace_context
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


class StructuredLoggingTest(unittest.TestCase):
    def test_production_json_output(self) -> None:
        stream = io.StringIO()
        configure_logging(env="production", level="INFO")
        handler = logging.StreamHandler(stream)
        
        # Point the root logger handler to our buffer
        root = logging.getLogger()
        formatter = root.handlers[0].formatter
        handler.setFormatter(formatter)
        root.handlers = [handler]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id="trace-prod-123")
        
        logger = structlog.get_logger("test.prod")
        logger.info("test_event", user_id="u_ana", amount_bucket="medium")

        output = stream.getvalue().strip()
        self.assertTrue(output.startswith("{") and output.endswith("}"))
        
        data = json.loads(output)
        self.assertEqual(data["event"], "test_event")
        self.assertEqual(data["trace_id"], "trace-prod-123")
        self.assertEqual(data["user_id"], "u_ana")
        self.assertEqual(data["amount_bucket"], "medium")
        self.assertEqual(data["level"], "info")
        self.assertEqual(data["logger"], "test.prod")
        self.assertIn("timestamp", data)

    def test_redaction_of_sensitive_keys(self) -> None:
        stream = io.StringIO()
        configure_logging(env="production", level="INFO")
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        handler.setFormatter(root.handlers[0].formatter)
        root.handlers = [handler]

        logger = structlog.get_logger("test.security")
        logger.info(
            "credentials_handled",
            api_key="secret-key-123",
            password="my_password",
            gemini_api_key="AIzaSy...",
            raw_audio=b"\x00\x01\x02",
            financial_payload={"balance": 50000},
            safe_metric="ok",
        )

        output = stream.getvalue().strip()
        data = json.loads(output)
        self.assertEqual(data["api_key"], "[REDACTED]")
        self.assertEqual(data["password"], "[REDACTED]")
        self.assertEqual(data["gemini_api_key"], "[REDACTED]")
        self.assertEqual(data["raw_audio"], "[REDACTED]")
        self.assertEqual(data["financial_payload"], "[REDACTED]")
        self.assertEqual(data["safe_metric"], "ok")

    def test_development_console_output(self) -> None:
        stream = io.StringIO()
        configure_logging(env="development", level="INFO")
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        handler.setFormatter(root.handlers[0].formatter)
        root.handlers = [handler]

        logger = structlog.get_logger("test.dev")
        logger.info("dev_message", status="active")

        output = stream.getvalue()
        self.assertIn("dev_message", output)
        self.assertIn("active", output)

    def test_standard_logging_compatibility(self) -> None:
        stream = io.StringIO()
        configure_logging(env="production", level="INFO")
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        handler.setFormatter(root.handlers[0].formatter)
        root.handlers = [handler]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id="trace-std-789")

        std_logger = logging.getLogger("thirdparty.library")
        std_logger.info("standard_log_message")

        output = stream.getvalue().strip()
        data = json.loads(output)
        self.assertEqual(data["event"], "standard_log_message")
        self.assertEqual(data["trace_id"], "trace-std-789")
        self.assertEqual(data["logger"], "thirdparty.library")

    def test_trace_middleware_binds_contextvars(self) -> None:
        stream = io.StringIO()
        configure_logging(env="production", level="INFO")
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        handler.setFormatter(root.handlers[0].formatter)
        root.handlers = [handler]

        settings = Settings(
            database_path=":memory:",
            enable_debug_endpoints=False,
            app_env="production",
        )
        app = create_app(provider=DummyLLM(), settings=settings)

        # Add a test route that logs from inside the request
        req_logger = structlog.get_logger("route.test")
        logged_events = []

        @app.get("/test-log")
        async def test_log_route():
            req_logger.info("inside_route_handler", action="verifying_context")
            logged_events.append(structlog.contextvars.get_contextvars())
            return {"status": "ok"}

        with TestClient(app) as client:
            res = client.get("/test-log", headers={"x-trace-id": "custom-trace-999"})
            self.assertEqual(res.status_code, 200)

        self.assertTrue(len(logged_events) > 0)
        self.assertEqual(logged_events[0].get("trace_id"), "custom-trace-999")
        self.assertEqual(logged_events[0].get("path"), "/test-log")
        self.assertEqual(logged_events[0].get("method"), "GET")


if __name__ == "__main__":
    unittest.main()
