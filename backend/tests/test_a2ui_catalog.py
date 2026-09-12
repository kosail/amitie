import unittest
from pathlib import Path

from ui_contract.catalog import CATALOG, CATALOG_ID
from ui_contract.prompt import build_system_prompt, catalog_summary
from ui_contract.validator import CatalogValidator, SdkValidator

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "A2UI_CATALOG.md"

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
}

VALID_PAYLOAD = [
    {"version": "v0.9", "createSurface": {"surfaceId": "debt-ana", "catalogId": CATALOG_ID}},
    {
        "version": "v0.9",
        "updateComponents": {
            "surfaceId": "debt-ana",
            "components": [
                {"id": "root", "component": "Column", "children": ["title", "debts", "strategy"], "gap": 16},
                {"id": "title", "component": "Heading", "text": "Tu situación actual", "level": 1},
                {"id": "debts", "component": "Column", "children": ["debt-bbva"], "gap": 8},
                {
                    "id": "debt-bbva",
                    "component": "DebtNode",
                    "creditor": "BBVA",
                    "balance": {"path": "/finance/liabilities/0/balance"},
                    "apr": {"path": "/finance/liabilities/0/apr"},
                    "minPayment": {"path": "/finance/liabilities/0/minPayment"},
                },
                {
                    "id": "strategy",
                    "component": "TradeoffScale",
                    "leftLabel": "Bajar mi pago mensual",
                    "rightLabel": "Pagar menos intereses",
                    "value": {"path": "/ui/strategyTilt"},
                    "action": {
                        "event": {
                            "name": "tune_tradeoff",
                            "context": {"value": "/ui/strategyTilt"},
                        }
                    },
                },
            ],
        },
    },
    {
        "version": "v0.9",
        "updateDataModel": {
            "surfaceId": "debt-ana",
            "path": "/finance",
            "value": {"liabilities": [{"balance": 48000, "apr": 0.54, "minPayment": 2900}]},
        },
    },
]


def _with_component(component: dict) -> list:
    return [
        {"version": "v0.9", "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID}},
        {"version": "v0.9", "updateComponents": {"surfaceId": "s", "components": [component]}},
    ]


class CatalogContractTest(unittest.TestCase):
    def test_catalog_id(self) -> None:
        self.assertEqual(CATALOG_ID, "amitie.standard.v1")

    def test_component_set_matches_m3_subset(self) -> None:
        self.assertEqual(set(CATALOG.component_names()), M3_SUBSET)

    def test_subset_documented_in_contract(self) -> None:
        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        for name in CATALOG.component_names():
            self.assertIn(f"`{name}`", contract, name)

    def test_catalog_summary(self) -> None:
        summary = catalog_summary()
        self.assertEqual(summary["catalog_id"], CATALOG_ID)
        self.assertIn("persist_ui", build_system_prompt(role_description="test"))


class CatalogValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = CatalogValidator()

    def test_valid_payload_passes(self) -> None:
        result = self.validator.validate(VALID_PAYLOAD)
        self.assertTrue(result.ok, result.issues)

    def test_unknown_component_rejected(self) -> None:
        result = self.validator.validate(_with_component({"id": "x", "component": "Bogus"}))
        self.assertFalse(result.ok)
        self.assertTrue(any("unknown component" in issue for issue in result.issues))

    def test_missing_required_prop_rejected(self) -> None:
        payload = _with_component(
            {"id": "x", "component": "DebtNode", "creditor": "BBVA", "apr": 0.5, "minPayment": 100}
        )
        result = self.validator.validate(payload)
        self.assertFalse(result.ok)
        self.assertTrue(any("missing required prop 'balance'" in issue for issue in result.issues))

    def test_unknown_action_rejected(self) -> None:
        payload = _with_component(
            {
                "id": "x",
                "component": "Button",
                "label": "Go",
                "action": {"event": {"name": "not_a_real_action", "context": {}}},
            }
        )
        result = self.validator.validate(payload)
        self.assertFalse(result.ok)
        self.assertTrue(any("unknown action" in issue for issue in result.issues))

    def test_dangling_child_reference_rejected(self) -> None:
        payload = _with_component(
            {"id": "root", "component": "Column", "children": ["missing"]}
        )
        result = self.validator.validate(payload)
        self.assertFalse(result.ok)
        self.assertTrue(any("unknown child reference" in issue for issue in result.issues))

    def test_bad_envelope_rejected(self) -> None:
        payload = [{"version": "v0.9", "createSurface": {"surfaceId": "s"}, "deleteSurface": {"surfaceId": "s"}}]
        result = self.validator.validate(payload)
        self.assertFalse(result.ok)
        self.assertTrue(any("exactly one message type" in issue for issue in result.issues))

    def test_unknown_catalog_rejected(self) -> None:
        payload = [{"version": "v0.9", "createSurface": {"surfaceId": "s", "catalogId": "other.v1"}}]
        result = self.validator.validate(payload)
        self.assertFalse(result.ok)
        self.assertTrue(any("unknown catalogId" in issue for issue in result.issues))

    def test_empty_payload_rejected(self) -> None:
        self.assertFalse(self.validator.validate([]).ok)


class SdkValidatorTest(unittest.TestCase):
    def test_adapter_never_raises(self) -> None:
        try:
            validator = SdkValidator()
        except Exception as exc:  # pragma: no cover - SDK unavailable
            self.skipTest(f"a2ui-agent-sdk unavailable: {exc}")
        # Documents that the SDK adapter itself is safe; the SDK validator is not active.
        result = validator.validate(VALID_PAYLOAD)
        self.assertIsInstance(result.ok, bool)


if __name__ == "__main__":
    unittest.main()
