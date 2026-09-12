import asyncio
import json
import logging
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from observability.context import current_trace_id, trace_context
from observability.logging import JsonFormatter
from observability.middleware import TraceMiddleware
from observability.tracing import TraceEvent, Tracer, new_trace_id


class TraceContextTest(unittest.TestCase):
    def test_context_round_trip(self) -> None:
        self.assertIsNone(current_trace_id())
        with trace_context("t1"):
            self.assertEqual(current_trace_id(), "t1")
        self.assertIsNone(current_trace_id())


class JsonFormatterTest(unittest.TestCase):
    def test_includes_trace_id(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)
        with trace_context("trace-123"):
            payload = json.loads(formatter.format(record))
        self.assertEqual(payload["trace_id"], "trace-123")
        self.assertEqual(payload["message"], "hello")


class TracerTest(unittest.TestCase):
    def test_record_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "obs.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                tracer = Tracer(database)
                trace_id = new_trace_id()
                await tracer.record(
                    trace_id,
                    TraceEvent(
                        kind="llm",
                        name="generate",
                        provider="gemini",
                        model="gemini-2.5-flash",
                        latency_ms=120,
                        tokens=42,
                    ),
                )
                history = await tracer.history(trace_id)
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["provider"], "gemini")
                self.assertEqual(history[0]["tokens"], 42)
                await database.close()

            asyncio.run(run())


class TraceMiddlewareTest(unittest.TestCase):
    def test_records_trace_and_sets_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "obs.sqlite3")

            async def app(scope, receive, send) -> None:
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"ok"})

            async def run() -> None:
                await apply_schema(database)
                middleware = TraceMiddleware(app, Tracer(database))
                messages = []

                async def send(message) -> None:
                    messages.append(message)

                async def receive():
                    return {"type": "http.request"}

                await middleware(
                    {"type": "http", "method": "POST", "path": "/api/message", "headers": []},
                    receive,
                    send,
                )

                self.assertEqual(messages[0]["status"], 200)
                headers = dict(messages[0]["headers"])
                self.assertIn(b"x-trace-id", headers)

                count = await database.fetch_one("SELECT COUNT(*) AS n FROM traces")
                self.assertEqual(count["n"], 1)
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
