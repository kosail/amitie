import unittest

from providers.speech_text import normalize_for_speech


class NormalizeForSpeechTest(unittest.TestCase):
    def test_currency_becomes_pesos(self) -> None:
        self.assertEqual(normalize_for_speech("$1,000.00"), "1000 pesos")
        self.assertEqual(normalize_for_speech("$7,000"), "7000 pesos")
        self.assertEqual(normalize_for_speech("$0.00"), "0 pesos")
        self.assertEqual(normalize_for_speech("$1,234,567.00"), "1234567 pesos")

    def test_currency_keeps_surrounding_words(self) -> None:
        self.assertEqual(
            normalize_for_speech("Cuesta $7,000 al mes"), "Cuesta 7000 pesos al mes"
        )

    def test_currency_does_not_duplicate_pesos_or_mxn(self) -> None:
        self.assertEqual(normalize_for_speech("$1,000 MXN"), "1000 pesos")
        self.assertEqual(normalize_for_speech("$1,000 pesos"), "1000 pesos")
        self.assertEqual(normalize_for_speech("1,000 pesos"), "1000 pesos")
        self.assertEqual(normalize_for_speech("5,000–200,000 MXN"), "5000 a 200000 pesos")

    def test_numeric_ranges(self) -> None:
        self.assertEqual(
            normalize_for_speech("$5,000–$200,000"),
            "5000 pesos a 200000 pesos",
        )
        self.assertEqual(normalize_for_speech("18%–36%"), "18% a 36%")

    def test_strips_thousands_separator(self) -> None:
        self.assertEqual(normalize_for_speech("Cuesta 7,000 al mes"), "Cuesta 7000 al mes")
        self.assertEqual(normalize_for_speech("1,234,567 pesos"), "1234567 pesos")

    def test_keeps_decimals(self) -> None:
        self.assertEqual(normalize_for_speech("$1,000.50"), "1000.50 pesos")
        self.assertEqual(normalize_for_speech("3.5%"), "3.5%")

    def test_leaves_unrelated_commas_and_dashes(self) -> None:
        self.assertEqual(normalize_for_speech("12,34"), "12,34")
        self.assertEqual(normalize_for_speech("1,2345"), "1,2345")
        self.assertEqual(normalize_for_speech("Hola, Ana"), "Hola, Ana")
        self.assertEqual(normalize_for_speech("La Mesa — una app"), "La Mesa — una app")

    def test_noop_on_plain_text(self) -> None:
        self.assertEqual(normalize_for_speech("Puedes ahorrar 3000 al mes"), "Puedes ahorrar 3000 al mes")
        self.assertEqual(normalize_for_speech("Mochilero. Confort"), "Mochilero. Confort")

    def test_empty_text(self) -> None:
        self.assertEqual(normalize_for_speech(""), "")

    def test_idempotent(self) -> None:
        once = normalize_for_speech("$1,234,567.00")
        self.assertEqual(normalize_for_speech(once), once)


if __name__ == "__main__":
    unittest.main()
