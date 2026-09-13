import asyncio
import unittest

from google.adk.models.llm_request import LlmRequest
from google.genai import types

from agent.model import GatewayLlm, ModelCallLimitError
from providers.base import LLMResult, ToolCall, Usage


class RecordingProvider:
    name = "recording"
    model = "recording"

    def __init__(self, result: LLMResult) -> None:
        self._result = result
        self.calls: list[dict] = []

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        self.calls.append({"messages": list(messages), "tools": list(tools or [])})
        return self._result


def build_request() -> LlmRequest:
    return LlmRequest(
        model="gateway",
        contents=[types.Content(role="user", parts=[types.Part.from_text(text="hola")])],
        config=types.GenerateContentConfig(
            system_instruction="eres un agente",
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name="get_x",
                            description="d",
                            parameters_json_schema={
                                "type": "object",
                                "properties": {"a": {"type": "string"}},
                                "required": ["a"],
                            },
                        )
                    ]
                )
            ],
        ),
    )


class GatewayLlmTest(unittest.TestCase):
    def test_tool_call_mapping(self) -> None:
        provider = RecordingProvider(
            LLMResult(
                text="",
                tool_calls=(ToolCall(name="get_x", arguments={"a": "1"}),),
                usage=Usage(1, 2, 3),
                provider="p",
                model="m",
            )
        )
        model = GatewayLlm(model="gateway", provider=provider, max_calls=3)

        async def run() -> None:
            responses = [response async for response in model.generate_content_async(build_request())]
            self.assertEqual(len(responses), 1)
            response = responses[0]
            self.assertFalse(response.turn_complete)
            self.assertEqual(response.content.parts[0].function_call.name, "get_x")
            self.assertEqual(response.usage_metadata.total_token_count, 3)

            call = provider.calls[0]
            self.assertEqual(call["messages"][0].role, "system")
            self.assertEqual(call["tools"][0].name, "get_x")
            self.assertEqual(call["tools"][0].parameters["required"], ["a"])

        asyncio.run(run())

    def test_text_mapping(self) -> None:
        provider = RecordingProvider(
            LLMResult(text="hola", tool_calls=(), usage=Usage(), provider="p", model="m")
        )
        model = GatewayLlm(model="gateway", provider=provider)

        async def run() -> None:
            response = await anext(model.generate_content_async(build_request()))
            self.assertTrue(response.turn_complete)
            self.assertEqual(response.content.parts[0].text, "hola")

        asyncio.run(run())

    def test_model_call_limit(self) -> None:
        provider = RecordingProvider(
            LLMResult(text="x", tool_calls=(), usage=Usage(), provider="p", model="m")
        )
        model = GatewayLlm(model="gateway", provider=provider, max_calls=1)

        async def run() -> None:
            await anext(model.generate_content_async(build_request()))
            with self.assertRaises(ModelCallLimitError):
                await anext(model.generate_content_async(build_request()))
            model.reset_calls()
            await anext(model.generate_content_async(build_request()))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
