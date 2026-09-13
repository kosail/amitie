import unittest

from providers.speech_text import normalize_for_speech


class NormalizeForSpeechTest(unittest.TestCase):
    def test_strips_thousands_separator(self) -> None:
        self.assertEqual(normalize_for_speech("Cuesta $7,000 al mes"), "Cuesta $7000 al mes")

    def test_strips_multiple_groups(self) -> None:
        self.assertEqual(normalize_for_speech("1,234,567 pesos"), "1234567 pesos")

    def test_keeps_decimals(self) -> None:
        self.assertEqual(normalize_for_speech("$7,000.50"), "$7000.50")

    def test_leaves_unrelated_commas(self) -> None:
        self.assertEqual(normalize_for_speech("12,34"), "12,34")
        self.assertEqual(normalize_for_speech("1,2345"), "1,2345")
        self.assertEqual(normalize_for_speech("Hola, Ana"), "Hola, Ana")

    def test_noop_on_plain_text(self) -> None:
        self.assertEqual(normalize_for_speech("Puedes ahorrar 3000 al mes"), "Puedes ahorrar 3000 al mes")
        self.assertEqual(normalize_for_speech("Mochilero. Confort"), "Mochilero. Confort")

    def test_empty_text(self) -> None:
        self.assertEqual(normalize_for_speech(""), "")

    def test_idempotent(self) -> None:
        once = normalize_for_speech("$1,234,567")
        self.assertEqual(normalize_for_speech(once), once)


if __name__ == "__main__":
    unittest.main()
