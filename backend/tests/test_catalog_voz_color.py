import unittest

from ui_contract.catalog import (
    CATALOG,
    CATALOGS,
    STANDARD_CATALOG_ID,
    VOZ_COLOR,
    VOZ_COLOR_ID,
)
from ui_contract.prompt import build_system_prompt
from ui_contract.validator import validate_messages


def _surface(catalog_id):
    return [
        {"version": "v0.9", "createSurface": {"surfaceId": "s", "catalogId": catalog_id}},
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Column", "children": ["h"]},
                    {"id": "h", "component": "Heading", "text": "Hola", "level": 1},
                ],
            },
        },
    ]


class VozColorCatalogTest(unittest.TestCase):
    def test_both_catalogs_registered(self) -> None:
        self.assertEqual(set(CATALOGS), {STANDARD_CATALOG_ID, VOZ_COLOR_ID})

    def test_shares_standard_component_set(self) -> None:
        self.assertEqual(VOZ_COLOR.component_names(), CATALOG.component_names())
        self.assertEqual(VOZ_COLOR.actions, CATALOG.actions)

    def test_voz_color_surface_validates(self) -> None:
        result = validate_messages(_surface(VOZ_COLOR_ID))
        self.assertTrue(result.ok, result.issues)

    def test_standard_surface_validates(self) -> None:
        result = validate_messages(_surface(STANDARD_CATALOG_ID))
        self.assertTrue(result.ok, result.issues)

    def test_unknown_catalog_rejected(self) -> None:
        result = validate_messages(_surface("amitie.other.v1"))
        self.assertFalse(result.ok)
        self.assertTrue(any("unknown catalogId" in issue for issue in result.issues))

    def test_prompt_targets_voz_color(self) -> None:
        prompt = build_system_prompt(role_description="test", catalog=VOZ_COLOR)
        self.assertIn(VOZ_COLOR_ID, prompt)
        self.assertIn("GoalJar", prompt)


if __name__ == "__main__":
    unittest.main()
