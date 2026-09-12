"""SpeechRecognitionSTT: bytes -> text via the SpeechRecognition library."""

import asyncio
import types
import unittest

from providers.base import ProviderResponseError, ProviderUnavailableError
from providers.speech_recognition_stt import SpeechRecognitionSTT


def make_sr(*, text="hola mundo", fail=None, seen=None):
    class UnknownValueError(Exception):
        pass

    class RequestError(Exception):
        pass

    class Recognizer:
        def record(self, source):
            return {"pcm": True}

        def recognize_google(self, data, language=None):
            if seen is not None:
                seen["language"] = language
            if fail == "unknown":
                raise UnknownValueError("no speech")
            if fail == "request":
                raise RequestError("network")
            return text

    class AudioFile:
        def __init__(self, fileobj):
            self._fileobj = fileobj

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return types.SimpleNamespace(
        UnknownValueError=UnknownValueError,
        RequestError=RequestError,
        Recognizer=Recognizer,
        AudioFile=AudioFile,
    )


class SpeechRecognitionSTTTest(unittest.TestCase):
    def test_transcribes_wav_with_language(self) -> None:
        seen = {}
        provider = SpeechRecognitionSTT(sr_module=make_sr(seen=seen), language="es-MX")
        result = asyncio.run(provider.transcribe(b"RIFF", mime="audio/wav"))
        self.assertEqual(result.text, "hola mundo")
        self.assertEqual(result.provider, "speech_recognition")
        self.assertEqual(result.language, "es-MX")
        self.assertEqual(seen["language"], "es-MX")

    def test_wav_passthrough_skips_conversion(self) -> None:
        def converter(audio, mime):  # pragma: no cover - must not be called
            raise AssertionError("converter should not run for WAV input")

        provider = SpeechRecognitionSTT(sr_module=make_sr(), converter=converter)
        result = asyncio.run(provider.transcribe(b"RIFF", mime="audio/wav"))
        self.assertEqual(result.text, "hola mundo")

    def test_mp3_is_converted_before_recognition(self) -> None:
        calls = {}

        def converter(audio, mime):
            calls["mime"] = mime
            return b"RIFF-converted"

        provider = SpeechRecognitionSTT(sr_module=make_sr(), converter=converter)
        result = asyncio.run(provider.transcribe(b"\xff\xfb", mime="audio/mpeg"))
        self.assertEqual(result.text, "hola mundo")
        self.assertEqual(calls["mime"], "audio/mpeg")

    def test_conversion_failure_is_unavailable(self) -> None:
        def converter(audio, mime):
            raise ProviderUnavailableError("ffmpeg required")

        provider = SpeechRecognitionSTT(sr_module=make_sr(), converter=converter)
        with self.assertRaises(ProviderUnavailableError):
            asyncio.run(provider.transcribe(b"\xff\xfb", mime="audio/mpeg"))

    def test_unknown_value_is_response_error(self) -> None:
        provider = SpeechRecognitionSTT(sr_module=make_sr(fail="unknown"))
        with self.assertRaises(ProviderResponseError):
            asyncio.run(provider.transcribe(b"RIFF", mime="audio/wav"))

    def test_request_error_is_unavailable(self) -> None:
        provider = SpeechRecognitionSTT(sr_module=make_sr(fail="request"))
        with self.assertRaises(ProviderUnavailableError):
            asyncio.run(provider.transcribe(b"RIFF", mime="audio/wav"))


if __name__ == "__main__":
    unittest.main()
