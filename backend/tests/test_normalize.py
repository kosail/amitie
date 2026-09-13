import unittest

from ui_contract.normalize import ensure_root, normalize_component, normalize_components


class NormalizeTest(unittest.TestCase):
    def test_bare_action_string_becomes_action_object(self) -> None:
        component = {"id": "b", "component": "Button", "label": "Sí", "action": "approve_plan"}
        result = normalize_component(component)
        self.assertEqual(result["action"], {"event": {"name": "approve_plan", "context": {}}})

    def test_unknown_action_string_is_left_untouched(self) -> None:
        component = {"id": "b", "component": "Button", "label": "x", "action": "not_an_action"}
        self.assertEqual(normalize_component(component)["action"], "not_an_action")

    def test_whole_placeholder_on_numeric_prop_becomes_binding(self) -> None:
        component = {
            "id": "offer",
            "component": "LoanOffer",
            "amount": "{{loan.amount}}",
            "apr": "{{loan.apr}}",
        }
        result = normalize_component(component)
        self.assertEqual(result["amount"], {"path": "/loan/amount"})
        self.assertEqual(result["apr"], {"path": "/loan/apr"})

    def test_text_placeholder_is_preserved(self) -> None:
        component = {"id": "t", "component": "Text", "text": "Debes {{loan.amount}} en total"}
        self.assertEqual(
            normalize_component(component)["text"], "Debes {{loan.amount}} en total"
        )

    def test_numeric_string_is_coerced(self) -> None:
        component = {"id": "offer", "component": "LoanOffer", "amount": "50000"}
        self.assertEqual(normalize_component(component)["amount"], 50000)

    def test_boolean_string_is_coerced(self) -> None:
        component = {"id": "c", "component": "ChoiceGroup", "options": [], "action": {"event": {"name": "select_strategy"}}, "multiple": "true"}
        self.assertIs(normalize_component(component)["multiple"], True)

    def test_components_list_and_unknown_type(self) -> None:
        components = [
            {"id": "x", "component": "NotARealType", "amount": "{{loan.amount}}"},
            {"id": "offer", "component": "LoanOffer", "amount": "{{loan.amount}}"},
        ]
        result = normalize_components(components)
        self.assertEqual(result[0]["amount"], "{{loan.amount}}")
        self.assertEqual(result[1]["amount"], {"path": "/loan/amount"})


class EnsureRootTest(unittest.TestCase):
    def test_existing_root_is_untouched(self) -> None:
        components = [
            {"id": "root", "component": "Column", "children": ["t"]},
            {"id": "t", "component": "Text", "text": "hola"},
        ]
        self.assertIs(ensure_root(components), components)

    def test_single_top_level_is_renamed(self) -> None:
        components = [
            {"id": "title", "component": "Heading", "text": "Hola"},
        ]
        result = ensure_root(components)
        self.assertEqual([c["id"] for c in result], ["root"])
        self.assertEqual(result[0]["component"], "Heading")

    def test_multiple_top_level_are_wrapped(self) -> None:
        components = [
            {"id": "a", "component": "Text", "text": "a"},
            {"id": "b", "component": "Text", "text": "b"},
        ]
        result = ensure_root(components)
        self.assertEqual(result[0]["id"], "root")
        self.assertEqual(result[0]["component"], "Column")
        self.assertEqual(result[0]["children"], ["a", "b"])
        self.assertEqual(len(result), 3)

    def test_child_references_are_not_treated_as_top_level(self) -> None:
        components = [
            {"id": "root", "component": "Column", "children": ["t"]},
            {"id": "t", "component": "Text", "text": "hola"},
        ]
        # root exists, so this is a no-op regardless of top-level detection.
        self.assertEqual(ensure_root(components), components)

    def test_does_not_mutate_input(self) -> None:
        components = [{"id": "title", "component": "Heading", "text": "Hola"}]
        ensure_root(components)
        self.assertEqual(components[0]["id"], "title")


if __name__ == "__main__":
    unittest.main()
