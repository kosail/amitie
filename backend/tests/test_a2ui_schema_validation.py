import json
import unittest

from ui_contract.catalog import CATALOG, CATALOG_ID
from ui_contract.schema_registry import catalog_schema
from ui_contract.validator import (
    CatalogValidator,
    JsonschemaValidator,
    validate_messages,
)

M3_SUBSET = {
    "Column",
    "Row",
    "Card",
    "Text",
    "Heading",
    "Divider",
    "Badge",
    "Button",
    "ChoiceGroup",
    "Slider",
    "DebtNode",
    "TradeoffScale",
    "BreakAlert",
    "PlanTable",
    "OfferCard",
    "NegotiationTranscript",
}

SAMPLE = [
    {"version": "v0.9", "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID}},
    {
        "version": "v0.9",
        "updateComponents": {
            "surfaceId": "s",
            "components": [
                {"id": "root", "component": "Column", "children": ["title", "debt", "scale"], "gap": 8},
                {"id": "title", "component": "Heading", "text": "Deuda total", "level": 1},
                {
                    "id": "debt",
                    "component": "DebtNode",
                    "creditor": "BBVA",
                    "balance": {"path": "/liabilities/0/balance"},
                    "apr": 0.54,
                    "minPayment": 2900,
                },
                {
                    "id": "scale",
                    "component": "TradeoffScale",
                    "leftLabel": "Pago mensual",
                    "rightLabel": "Intereses",
                    "value": {"path": "/ui/tilt"},
                    "action": {
                        "event": {"name": "tune_tradeoff", "context": {"value": "/ui/tilt"}}
                    },
                },
            ],
        },
    },
    {"version": "v0.9", "updateDataModel": {"surfaceId": "s", "path": "/", "value": {}}},
]


def _with_button(action_name: str) -> list:
    return [
        {"version": "v0.9", "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID}},
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Column", "children": ["go"]},
                    {
                        "id": "go",
                        "component": "Button",
                        "label": "Go",
                        "action": {"event": {"name": action_name, "context": {}}},
                    },
                ],
            },
        },
    ]


class JsonschemaValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = JsonschemaValidator()

    def test_valid_payload_passes(self) -> None:
        result = self.validator.validate(SAMPLE)
        self.assertTrue(result.ok, result.issues)

    def test_combined_validation_passes(self) -> None:
        result = validate_messages(SAMPLE)
        self.assertTrue(result.ok, result.issues)

    def test_unknown_component_rejected(self) -> None:
        payload = [
            {"version": "v0.9", "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID}},
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{"id": "x", "component": "Bogus"}],
                },
            },
        ]
        self.assertFalse(self.validator.validate(payload).ok)

    def test_missing_required_prop_rejected(self) -> None:
        payload = [
            {"version": "v0.9", "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID}},
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [
                        {"id": "d", "component": "DebtNode", "creditor": "BBVA", "apr": 0.5, "minPayment": 100}
                    ],
                },
            },
        ]
        self.assertFalse(self.validator.validate(payload).ok)

    def test_bad_version_rejected(self) -> None:
        payload = [{"version": "v1.0", "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID}}]
        self.assertFalse(self.validator.validate(payload).ok)

    def test_relative_catalog_refs_resolve(self) -> None:
        schema = catalog_schema()
        self.assertEqual(schema["catalogId"], CATALOG_ID)
        self.assertEqual(set(schema["components"]), M3_SUBSET)
        # Validating SAMPLE exercises the relative `catalog.json` and
        # `common_types.json` refs; a resolution failure would surface here.
        self.assertTrue(self.validator.validate(SAMPLE).ok)


class SemanticPassTest(unittest.TestCase):
    def test_unknown_action_is_caught_by_semantics(self) -> None:
        payload = _with_button("not_a_real_action")
        # JSON Schema treats the action name as a free string, so it passes...
        self.assertTrue(JsonschemaValidator().validate(payload).ok)
        # ...but the semantic pass rejects it, and the combined validator fails.
        self.assertFalse(CatalogValidator().validate(payload).ok)
        self.assertFalse(validate_messages(payload).ok)

    def test_known_action_passes_both(self) -> None:
        payload = _with_button("approve_plan")
        self.assertTrue(validate_messages(payload).ok)


if __name__ == "__main__":
    unittest.main()
