import asyncio
import base64
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.voice.server import build_voice_server
from providers.base import ProviderUnavailableError
from providers.voice import SynthesisResult, TranscriptionResult


class FakeTTS:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0
        self.texts: list[str] = []

    async def synthesize(self, text, voice_id="", speed=1.0):
        self.calls += 1
        self.texts.append(text)
        return SynthesisResult(b"BYTES:" + text.encode(), "audio/mpeg", voice_id or "v", self.name)


class FailingTTS:
    name = "failing"

    async def synthesize(self, text, voice_id="", speed=1.0):
        raise ProviderUnavailableError("no audio device")


class FakeSTT:
    name = "fake-stt"

    async def transcribe(self, audio, mime="audio/mpeg", language="es-MX"):
        return TranscriptionResult("texto:" + audio.decode(errors="ignore"), self.name, language)


class VoiceToolsTest(unittest.TestCase):
    def test_synthesis_is_cached_by_text_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "voice.sqlite3")
            tts = FakeTTS()
            server = build_voice_server(
                database, tts, FakeSTT(), cache_dir=str(Path(tmp) / "audio")
            )

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with InProcessToolbox({"voice": server}) as toolbox:
                    first = await toolbox.call(
                        "synthesize_speech",
                        {"text": "Hola Ana", "user_id": "u_don", "voice_id": "v1"},
                    )
                    self.assertEqual(first["status"], "ok")
                    self.assertFalse(first["cached"])
                    self.assertTrue(first["audio_ref"].startswith("/api/audio/"))

                    second = await toolbox.call(
                        "synthesize_speech",
                        {"text": "Hola Ana", "user_id": "u_don", "voice_id": "v1"},
                    )
                    self.assertTrue(second["cached"])
                    self.assertEqual(first["audio_id"], second["audio_id"])

                    meta = await toolbox.call("get_audio", {"asset_id": first["audio_id"]})
                    self.assertEqual(meta["status"], "ok")
                    self.assertTrue(Path(meta["file_path"]).is_file())

                rows = await database.fetch_all("SELECT id FROM audio_assets")
                self.assertEqual(len(rows), 1)
                await database.close()

            asyncio.run(run())
            self.assertEqual(tts.calls, 1)

    def test_speech_text_is_normalized_for_provider_but_stored_text_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "voice.sqlite3")
            tts = FakeTTS()
            server = build_voice_server(
                database, tts, FakeSTT(), cache_dir=str(Path(tmp) / "audio")
            )

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with InProcessToolbox({"voice": server}) as toolbox:
                    first = await toolbox.call(
                        "synthesize_speech",
                        {"text": "Cuesta $7,000.00 al mes", "user_id": "u_don", "voice_id": "v1"},
                    )
                    self.assertEqual(first["status"], "ok")
                    self.assertFalse(first["cached"])

                    meta = await toolbox.call("get_audio", {"asset_id": first["audio_id"]})
                    self.assertEqual(meta["text"], "Cuesta $7,000.00 al mes")

                    second = await toolbox.call(
                        "synthesize_speech",
                        {"text": "Cuesta $7,000.00 al mes", "user_id": "u_don", "voice_id": "v1"},
                    )
                    self.assertTrue(second["cached"])
                    self.assertEqual(first["audio_id"], second["audio_id"])
                await database.close()

            asyncio.run(run())
            self.assertEqual(tts.texts, ["Cuesta 7000 pesos al mes"])
            self.assertEqual(tts.calls, 1)

    def test_cache_key_uses_the_spoken_form(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "voice.sqlite3")
            tts = FakeTTS()
            server = build_voice_server(
                database, tts, FakeSTT(), cache_dir=str(Path(tmp) / "audio")
            )

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with InProcessToolbox({"voice": server}) as toolbox:
                    first = await toolbox.call(
                        "synthesize_speech",
                        {"text": "$1,000.00", "user_id": "u_don", "voice_id": "v1"},
                    )
                    second = await toolbox.call(
                        "synthesize_speech",
                        {"text": "1000 pesos", "user_id": "u_don", "voice_id": "v1"},
                    )
                    self.assertEqual(first["status"], "ok")
                    self.assertFalse(first["cached"])
                    self.assertTrue(second["cached"])
                    self.assertEqual(first["audio_id"], second["audio_id"])
                await database.close()

            asyncio.run(run())
            self.assertEqual(tts.texts, ["1000 pesos"])
            self.assertEqual(tts.calls, 1)

    def test_unavailable_tts_degrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "voice.sqlite3")
            server = build_voice_server(
                database, FailingTTS(), FakeSTT(), cache_dir=str(Path(tmp) / "audio")
            )

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with InProcessToolbox({"voice": server}) as toolbox:
                    result = await toolbox.call(
                        "synthesize_speech", {"text": "Hola", "user_id": "u_don"}
                    )
                    self.assertEqual(result["status"], "unavailable")
                    self.assertEqual(result["text"], "Hola")
                await database.close()

            asyncio.run(run())

    def test_transcribe_decodes_base64(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "voice.sqlite3")
            server = build_voice_server(
                database, FakeTTS(), FakeSTT(), cache_dir=str(Path(tmp) / "audio")
            )

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                audio = base64.b64encode(b"voz").decode()
                async with InProcessToolbox({"voice": server}) as toolbox:
                    result = await toolbox.call(
                        "transcribe_audio", {"audio_b64": audio, "language": "es-MX"}
                    )
                    self.assertEqual(result["status"], "ok")
                    self.assertEqual(result["text"], "texto:voz")

                    bad = await toolbox.call(
                        "transcribe_audio", {"audio_b64": "not-base64!!"}
                    )
                    self.assertEqual(bad["status"], "error")
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
