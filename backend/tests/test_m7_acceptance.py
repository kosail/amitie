"""M7 acceptance: automatic accessibility, speech payload, audio in/out.

Network-free: TTS/STT are fakes and the LLM is a scripted provider.
"""

import asyncio
import base64
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
from providers.voice import SynthesisResult, TranscriptionResult
from ui_contract.catalog import STANDARD_CATALOG_ID, VOZ_COLOR_ID
from ui_contract.validator import validate_messages

ACCESSIBLE_COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["h", "t"], "gap": 12},
    {"id": "h", "component": "Heading", "text": "Tu plan de ahorro", "level": 1},
    {"id": "t", "component": "Text", "text": "Puedes guardar 3000 al mes"},
]

SPEECH = "Tu plan de ahorro. Puedes guardar 3000 al mes"


class FakeTTS:
    name = "fake-tts"

    async def synthesize(self, text, voice_id="", speed=1.0):
        return SynthesisResult(b"BYTES:" + text.encode(), "audio/mpeg", voice_id or "v", self.name)


class FakeSTT:
    name = "fake-stt"

    def __init__(self, text="quiero ahorrar para un viaje"):
        self._text = text

    async def transcribe(self, audio, mime="audio/mpeg", language="es-MX"):
        return TranscriptionResult(self._text, self.name, language)


def tool_call(name, arguments):
    return LLMResult(
        text="",
        tool_calls=(ToolCall(name=name, arguments=arguments),),
        usage=Usage(1, 1, 2),
        provider="scripted",
        model="scripted",
    )


def text_result(text):
    return LLMResult(
        text=text, tool_calls=(), usage=Usage(1, 1, 2), provider="scripted", model="scripted"
    )


def persist_call(user_id, speech=""):
    return tool_call(
        "persist_ui",
        {
            "user_id": user_id,
            "domain": "loans_credits",
            "catalog_id": STANDARD_CATALOG_ID,
            "components": ACCESSIBLE_COMPONENTS,
            "data_model": {},
            "speech": speech,
        },
    )


class QueueProvider:
    name = "scripted"
    model = "scripted"

    def __init__(self) -> None:
        self._queue: list[LLMResult] = []
        self.seen: list[str] = []

    def push(self, *results: LLMResult) -> None:
        self._queue.extend(results)

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        self.seen.append(" ".join(m.content or "" for m in messages))
        if self._queue:
            return self._queue.pop(0)
        return text_result("(sin guion)")


def _create_catalog(a2ui):
    return next(m for m in a2ui if "createSurface" in m)["createSurface"]["catalogId"]


def _data_model(a2ui):
    return next(m for m in a2ui if "updateDataModel" in m)["updateDataModel"]["value"]


class M7AcceptanceTest(unittest.TestCase):
    def test_accessible_flow_and_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "m7.sqlite3")

            async def prep() -> None:
                database = LocalSQLiteDatabase(db_path)
                await apply_schema(database)
                await seed(database)
                await database.close()

            asyncio.run(prep())

            provider = QueueProvider()
            settings = Settings(
                database_path=db_path, audio_cache_dir=str(Path(tmp) / "audio")
            )
            app = create_app(provider=provider, settings=settings, tts=FakeTTS(), stt=FakeSTT())

            with TestClient(app) as client:
                don = client.post("/api/session", json={"user_id": "u_don"}).json()["session_id"]

                # Accessible text turn: catalog pinned + speech synthesized.
                provider.push(persist_call("u_don", SPEECH), text_result("Listo."))
                message = client.post(
                    "/api/message", json={"session_id": don, "text": "ayúdame a ahorrar"}
                )
                body = message.json()
                self.assertEqual(body["status"], "ok", body)
                self.assertEqual(body["catalog_id"], VOZ_COLOR_ID)
                self.assertEqual(_create_catalog(body["a2ui"]), VOZ_COLOR_ID)
                self.assertTrue(body["audio_ref"].startswith("/api/audio/"))
                self.assertEqual(_data_model(body["a2ui"])["speech"]["text"], SPEECH)
                self.assertTrue(validate_messages(body["a2ui"]).ok)

                # The audio asset is served.
                asset_id = body["audio_ref"].rsplit("/", 1)[-1]
                audio = client.get(f"/api/audio/{asset_id}")
                self.assertEqual(audio.status_code, 200)
                self.assertEqual(audio.content, b"BYTES:" + SPEECH.encode())
                self.assertEqual(client.get("/api/audio/nope").status_code, 404)

                # Audio input is transcribed then drives the agent.
                provider.push(persist_call("u_don", SPEECH), text_result("Entendido."))
                audio_b64 = base64.b64encode(b"voz").decode()
                voice = client.post(
                    "/api/message",
                    json={"session_id": don, "audio_b64": audio_b64, "language": "es-MX"},
                )
                self.assertEqual(voice.json()["status"], "ok", voice.json())
                self.assertTrue(
                    any("quiero ahorrar para un viaje" in text for text in provider.seen),
                    "the transcription must reach the agent",
                )

                # Contrast: a non-flagged user stays on the standard catalog.
                ana = client.post("/api/session", json={"user_id": "u_ana"}).json()["session_id"]
                provider.push(persist_call("u_ana", SPEECH), text_result("Listo."))
                standard = client.post(
                    "/api/message", json={"session_id": ana, "text": "hola"}
                ).json()
                self.assertEqual(standard["status"], "ok")
                self.assertEqual(standard["catalog_id"], STANDARD_CATALOG_ID)
                # Audio now plays for every audience; standard speaks the reply text.
                self.assertTrue(standard["audio_ref"].startswith("/api/audio/"))
                self.assertIn("speech", _data_model(standard["a2ui"]))


if __name__ == "__main__":
    unittest.main()
