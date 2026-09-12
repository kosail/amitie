import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx2

from config import Settings
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from observability.tracing import Tracer
from providers.base import (
    ChatMessage,
    LLMResult,
    ProviderUnavailableError,
    ToolCall,
    ToolSpec,
    Usage,
)
from providers.deepseek import DeepSeekLLM
from providers.gateway import FallbackLLM
from providers.registry import build_llm

try:  # optional: only needed for the Gemini construction test
    import google.genai  # noqa: F401

    HAS_GENAI = True
except Exception:  # pragma: no cover - environment dependent
    HAS_GENAI = False


class FakeProvider:
    def __init__(self, name: str, model: str = "fake-model", error: Exception | None = None) -> None:
        self.name = name
        self.model = model
        self.error = error
        self.calls = 0

    async def generate(self, messages, tools=None, response_schema=None, temperature=None) -> LLMResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return LLMResult(
            text="hola",
            tool_calls=(),
            usage=Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            provider=self.name,
            model=self.model,
        )


CANNED_DEEPSEEK = {
    "choices": [
        {
            "message": {
                "content": "ok",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_liabilities",
                            "arguments": '{"user_id": "u_ana"}',
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    "model": "deepseek-flash",
}


class FallbackTest(unittest.TestCase):
    def test_failover_returns_fallback_result(self) -> None:
        async def run() -> None:
            primary = FakeProvider("gemini", error=ProviderUnavailableError("quota"))
            fallback = FakeProvider("deepseek")
            gateway = FallbackLLM(primary, fallback, cooldown_seconds=0)
            result = await gateway.generate([ChatMessage(role="user", content="hi")])
            self.assertEqual(result.provider, "deepseek")
            self.assertEqual(primary.calls, 1)
            self.assertEqual(fallback.calls, 1)

        asyncio.run(run())

    def test_both_failing_raises(self) -> None:
        async def run() -> None:
            primary = FakeProvider("gemini", error=ProviderUnavailableError("quota"))
            fallback = FakeProvider("deepseek", error=ProviderUnavailableError("down"))
            gateway = FallbackLLM(primary, fallback, cooldown_seconds=0)
            with self.assertRaises(ProviderUnavailableError):
                await gateway.generate([ChatMessage(role="user", content="hi")])

        asyncio.run(run())

    def test_cooldown_skips_primary_until_expiry(self) -> None:
        async def run() -> None:
            primary = FakeProvider("gemini", error=ProviderUnavailableError("quota"))
            fallback = FakeProvider("deepseek")
            now = {"t": 100.0}
            gateway = FallbackLLM(
                primary, fallback, cooldown_seconds=30, clock=lambda: now["t"]
            )
            await gateway.generate([ChatMessage(role="user", content="1")])
            self.assertEqual(primary.calls, 1)

            now["t"] = 110.0  # still within cooldown
            await gateway.generate([ChatMessage(role="user", content="2")])
            self.assertEqual(primary.calls, 1)
            self.assertEqual(fallback.calls, 2)

            now["t"] = 200.0  # cooldown expired
            await gateway.generate([ChatMessage(role="user", content="3")])
            self.assertEqual(primary.calls, 2)
            self.assertEqual(fallback.calls, 3)

        asyncio.run(run())

    def test_gateway_records_traces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "providers.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                tracer = Tracer(database)
                primary = FakeProvider("gemini", error=ProviderUnavailableError("429"))
                fallback = FakeProvider("deepseek")
                gateway = FallbackLLM(
                    primary, fallback, tracer=tracer, cooldown_seconds=30
                )
                await gateway.generate([ChatMessage(role="user", content="hi")])

                rows = await database.fetch_all(
                    "SELECT provider, error, tokens FROM traces"
                )
                self.assertEqual(len(rows), 2)
                by_provider = {row["provider"]: row for row in rows}
                self.assertEqual(set(by_provider), {"gemini", "deepseek"})
                self.assertIsNotNone(by_provider["gemini"]["error"])
                self.assertEqual(by_provider["deepseek"]["tokens"], 3)
                await database.close()

            asyncio.run(run())


class RegistryTest(unittest.TestCase):
    def test_unknown_provider_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_llm(Settings(llm_provider="nope"))

    def test_builds_deepseek(self) -> None:
        provider = build_llm(Settings(llm_provider="deepseek", deepseek_api_key="test"))
        self.assertEqual(provider.name, "deepseek")

    @unittest.skipUnless(HAS_GENAI, "google-genai is not installed")
    def test_builds_gemini(self) -> None:
        provider = build_llm(Settings(llm_provider="gemini", gemini_api_key="test"))
        self.assertEqual(provider.name, "gemini")


class _FakeFunctionCall:
    def __init__(self, name: str, args: dict) -> None:
        self.name = name
        self.args = args


class _FakeUsageMetadata:
    prompt_token_count = 10
    candidates_token_count = 5
    total_token_count = 15


class _FakeGeminiResponse:
    text = "hola"
    usage_metadata = _FakeUsageMetadata()

    def __init__(self) -> None:
        self.function_calls = [_FakeFunctionCall("get_liabilities", {"user_id": "u_ana"})]


class _FakeGeminiModels:
    def __init__(self) -> None:
        self.kwargs = None

    async def generate_content(self, **kwargs):
        self.kwargs = kwargs
        return _FakeGeminiResponse()


class _FakeGeminiAio:
    def __init__(self) -> None:
        self.models = _FakeGeminiModels()


class _FakeGeminiClient:
    def __init__(self) -> None:
        self.aio = _FakeGeminiAio()


class _FakePart:
    def __init__(self, name: str, args: dict, signature: bytes | None = None) -> None:
        self.function_call = _FakeFunctionCall(name, args)
        self.thought_signature = signature


class _FakeCandidateResponse:
    text = "hola"
    usage_metadata = _FakeUsageMetadata()

    def __init__(self, signature: bytes | None) -> None:
        part = _FakePart("get_liabilities", {"user_id": "u_ana"}, signature)
        self.candidates = [type("C", (), {"content": type("K", (), {"parts": [part]})()})()]


class _FakeCandidateModels:
    def __init__(self, signature: bytes | None) -> None:
        self._signature = signature

    async def generate_content(self, **kwargs):
        return _FakeCandidateResponse(self._signature)


class _FakeCandidateClient:
    def __init__(self, signature: bytes | None = None) -> None:
        self.aio = type("Aio", (), {"models": _FakeCandidateModels(signature)})()


class GeminiAdapterTest(unittest.TestCase):
    @unittest.skipUnless(HAS_GENAI, "google-genai is not installed")
    def test_maps_response_and_builds_config(self) -> None:
        from providers.gemini import GeminiLLM

        async def run() -> None:
            client = _FakeGeminiClient()
            provider = GeminiLLM(api_key="", model="gemini-2.5-flash", client=client)
            result = await provider.generate(
                [ChatMessage(role="user", content="hola")],
                tools=[
                    ToolSpec(
                        name="get_liabilities",
                        description="d",
                        parameters={"type": "object"},
                    )
                ],
            )
            self.assertEqual(result.text, "hola")
            self.assertEqual(result.tool_calls[0].name, "get_liabilities")
            self.assertEqual(result.usage.total_tokens, 15)
            self.assertEqual(result.provider, "gemini")
            self.assertIsNotNone(client.aio.models.kwargs["config"])

        asyncio.run(run())

    @unittest.skipUnless(HAS_GENAI, "google-genai is not installed")
    def test_tool_response_uses_valid_roles(self) -> None:
        from providers.gemini import _to_contents

        messages = [
            ChatMessage(role="user", content="tengo deudas"),
            ChatMessage(
                role="assistant",
                content="",
                tool_calls=(
                    ToolCall(name="get_financial_context", arguments={"user_id": "u_ana"}),
                ),
            ),
            ChatMessage(
                role="tool",
                name="get_financial_context",
                content='{"totals": {"debt": 1}}',
            ),
            ChatMessage(role="assistant", content="listo"),
        ]
        contents = _to_contents(messages)
        roles = [content.role for content in contents]
        # Regression: Gemini only accepts "user"/"model"; a function response
        # must NOT be role "tool".
        self.assertTrue(set(roles) <= {"user", "model"}, roles)
        self.assertEqual(roles, ["user", "model", "user", "model"])
        tool_content = contents[2]
        self.assertEqual(tool_content.role, "user")
        response = tool_content.parts[0].function_response
        self.assertIsNotNone(response)
        self.assertEqual(response.name, "get_financial_context")
        self.assertEqual(dict(response.response), {"totals": {"debt": 1}})

    @unittest.skipUnless(HAS_GENAI, "google-genai is not installed")
    def test_to_result_preserves_thought_signature(self) -> None:
        from providers.gemini import GeminiLLM

        async def run() -> None:
            client = _FakeCandidateClient(b"sig-123")
            provider = GeminiLLM(api_key="", model="gemini-3.6-flash", client=client)
            result = await provider.generate([ChatMessage(role="user", content="hi")])
            self.assertEqual(result.tool_calls[0].thought_signature, b"sig-123")

        asyncio.run(run())

    @unittest.skipUnless(HAS_GENAI, "google-genai is not installed")
    def test_assistant_call_echoes_signature_or_sentinel(self) -> None:
        from providers.gemini import _SKIP_SIGNATURE, _to_contents

        contents = _to_contents(
            [
                ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=(
                        ToolCall(name="a", arguments={}, thought_signature=b"real"),
                        ToolCall(name="b", arguments={}),
                    ),
                )
            ]
        )
        model = contents[0]
        self.assertEqual(model.role, "model")
        self.assertEqual(model.parts[0].thought_signature, b"real")
        self.assertEqual(model.parts[1].thought_signature, _SKIP_SIGNATURE)


class DeepSeekTest(unittest.TestCase):
    def test_parses_tool_calls_and_usage(self) -> None:
        seen = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            seen["payload"] = json.loads(request.content)
            return httpx2.Response(200, json=CANNED_DEEPSEEK)

        async def run() -> None:
            client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
            provider = DeepSeekLLM(api_key="test", model="deepseek-flash", client=client)
            try:
                result = await provider.generate([ChatMessage(role="user", content="hola")])
            finally:
                await client.aclose()

            self.assertEqual(result.text, "ok")
            self.assertEqual(result.tool_calls[0].name, "get_liabilities")
            self.assertEqual(result.tool_calls[0].arguments, {"user_id": "u_ana"})
            self.assertEqual(result.usage.total_tokens, 15)
            self.assertEqual(result.provider, "deepseek")
            self.assertEqual(seen["payload"]["model"], "deepseek-flash")
            self.assertEqual(seen["payload"]["thinking"], {"type": "disabled"})

        asyncio.run(run())

    def test_rate_limit_raises_unavailable(self) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(429, json={"error": "rate limited"})

        async def run() -> None:
            client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
            provider = DeepSeekLLM(api_key="test", model="deepseek-flash", client=client)
            try:
                with self.assertRaises(ProviderUnavailableError):
                    await provider.generate([ChatMessage(role="user", content="hi")])
            finally:
                await client.aclose()

        asyncio.run(run())


    def test_tool_call_id_matches_tool_message(self) -> None:
        seen = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            seen["payload"] = json.loads(request.content)
            return httpx2.Response(200, json=CANNED_DEEPSEEK)

        async def run() -> None:
            client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
            provider = DeepSeekLLM(api_key="test", model="deepseek-flash", client=client)
            messages = [
                ChatMessage(role="user", content="hi"),
                ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=(ToolCall(name="get_liabilities", arguments={}),),
                ),
                ChatMessage(role="tool", name="get_liabilities", content="{}"),
            ]
            try:
                await provider.generate(messages)
            finally:
                await client.aclose()

            assistant = next(m for m in seen["payload"]["messages"] if m["role"] == "assistant")
            tool = next(m for m in seen["payload"]["messages"] if m["role"] == "tool")
            # Regression: the assistant tool_call id and the tool result must match.
            self.assertEqual(assistant["tool_calls"][0]["id"], tool["tool_call_id"])
            self.assertEqual(tool["tool_call_id"], "call_get_liabilities")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
