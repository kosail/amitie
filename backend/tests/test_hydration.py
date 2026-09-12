import unittest

from hydration.placeholders import collect_placeholders, resolve_placeholders
from hydration.service import hydrate_components


class PlaceholderTest(unittest.TestCase):
    def test_resolve_nested(self) -> None:
        context = {"a": {"b": [{"c": 5}]}, "name": "Ana"}
        self.assertEqual(
            resolve_placeholders("{{name}} tiene {{a.b.0.c}}", context), "Ana tiene 5"
        )

    def test_whole_string_preserves_type(self) -> None:
        context = {"a": {"b": [{"c": 5}]}}
        self.assertEqual(resolve_placeholders("{{a.b.0.c}}", context), 5)
        self.assertEqual(resolve_placeholders("  {{a.b.0.c}}  ", context), 5)

    def test_missing_key(self) -> None:
        self.assertIsNone(resolve_placeholders("{{nope.x}}", {}))
        self.assertEqual(resolve_placeholders("x={{nope}}", {}), "x=")

    def test_collect(self) -> None:
        self.assertEqual(
            collect_placeholders({"t": "{{a}} {{b.c}}", "l": ["{{d}}"]}),
            {"a", "b.c", "d"},
        )

    def test_hydrate_components(self) -> None:
        template = [{"id": "t", "component": {"Heading": {"text": "{{x}}"}}}]
        self.assertEqual(
            hydrate_components(template, {"x": 7})[0]["component"]["Heading"]["text"], 7
        )


if __name__ == "__main__":
    unittest.main()
