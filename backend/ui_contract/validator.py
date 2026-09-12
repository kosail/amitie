"""A2UI payload validation.

`JsonschemaValidator` validates payloads against the A2UI SDK's vendored v0.9
schemas (message envelopes, common types, and our SDK-format catalog), using
`jsonschema` for cross-document `$ref` resolution (INV-011).

`CatalogValidator` is kept as a fast semantic pass that JSON Schema cannot
express: it checks the known `catalogId` and known action names, and gives
friendlier messages. `validate_messages` runs JSON Schema first, then semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from jsonschema.exceptions import ValidationError

from .catalog import CATALOGS, STANDARD_CATALOG_ID, Catalog
from .schema_registry import message_validator

_NUMBER_TYPES = (int, float)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: tuple[str, ...] = ()

    def raise_for_errors(self) -> None:
        if not self.ok:
            raise A2uiValidationError("; ".join(self.issues))


class A2uiValidationError(ValueError):
    """Raised when an A2UI payload violates the catalog contract."""


class UiValidator(Protocol):
    def validate(self, messages: Any) -> ValidationResult: ...


def _snake(name: str) -> str:
    return "".join(("_" + c.lower()) if c.isupper() else c for c in name)


def _is_binding(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("path"), str)


def _is_number(value: Any) -> bool:
    return isinstance(value, _NUMBER_TYPES) and not isinstance(value, bool)


def _check_prop(token: str, value: Any) -> str | None:
    if token.startswith("enum:"):
        allowed = token.split(":", 1)[1].split(",")
        if str(value) in allowed:
            return None
        return f"expected one of {allowed}, got {value!r}"
    if token == "string":
        return None if isinstance(value, str) else f"expected string, got {type(value).__name__}"
    if token == "number":
        return None if _is_number(value) else f"expected number, got {type(value).__name__}"
    if token == "boolean":
        return None if isinstance(value, bool) else f"expected boolean, got {type(value).__name__}"
    if token == "dynamicString":
        return None if isinstance(value, str) or _is_binding(value) else "expected string or binding"
    if token == "dynamicNumber":
        return None if _is_number(value) or _is_binding(value) else "expected number or binding"
    if token == "dynamicBool":
        return None if isinstance(value, bool) or _is_binding(value) else "expected boolean or binding"
    if token == "dynamic":
        if isinstance(value, (str, bool)) or _is_number(value) or _is_binding(value):
            return None
        return "expected a literal or binding"
    if token == "idArray":
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return None
        return "expected a list of component ids"
    if token == "array":
        return None if isinstance(value, list) else f"expected array, got {type(value).__name__}"
    if token == "object":
        return None if isinstance(value, dict) else f"expected object, got {type(value).__name__}"
    if token == "any":
        return None
    return f"unsupported prop token {token!r}"


class CatalogValidator:
    def __init__(
        self, catalog: Catalog | None = None, catalogs: Mapping[str, Catalog] | None = None
    ) -> None:
        if catalog is not None:
            self._catalogs = {catalog.catalog_id: catalog}
        elif catalogs is not None:
            self._catalogs = dict(catalogs)
        else:
            self._catalogs = dict(CATALOGS)
        self._default = self._catalogs.get(STANDARD_CATALOG_ID) or next(iter(self._catalogs.values()))

    def _catalog_for_surface(self, surfaces: dict[str, str], surface_id: Any) -> Catalog:
        catalog_id = surfaces.get(surface_id) if isinstance(surface_id, str) else None
        return self._catalogs.get(catalog_id) or self._default

    def validate(self, messages: Any) -> ValidationResult:
        issues: list[str] = []
        if not isinstance(messages, list) or not messages:
            return ValidationResult(False, ("payload must be a non-empty list of A2UI messages",))

        surfaces: dict[str, str] = {}
        for index, message in enumerate(messages):
            location = f"messages[{index}]"
            if not isinstance(message, dict):
                issues.append(f"{location}: message must be an object")
                continue
            if message.get("version") != self._default.version:
                issues.append(f"{location}: version must be {self._default.version!r}")
            kinds = [key for key in message if key != "version"]
            if len(kinds) != 1:
                issues.append(f"{location}: exactly one message type is required, found {kinds}")
                continue
            kind = kinds[0]
            if kind not in self._default.messages:
                issues.append(f"{location}: unknown message type {kind!r}")
                continue
            body = message[kind]
            if not isinstance(body, dict):
                issues.append(f"{location}.{kind}: body must be an object")
                continue
            getattr(self, f"_validate_{_snake(kind)}")(body, f"{location}.{kind}", surfaces, issues)

        return ValidationResult(not issues, tuple(issues))

    def _require_surface(self, body: dict, location: str, issues: list[str]) -> None:
        if not isinstance(body.get("surfaceId"), str):
            issues.append(f"{location}: surfaceId must be a string")

    def _validate_create_surface(
        self, body: dict, location: str, surfaces: dict[str, str], issues: list[str]
    ) -> None:
        self._require_surface(body, location, issues)
        surface_id = body.get("surfaceId")
        catalog_id = body.get("catalogId")
        if catalog_id is None:
            if isinstance(surface_id, str):
                surfaces[surface_id] = self._default.catalog_id
        elif not isinstance(catalog_id, str) or catalog_id not in self._catalogs:
            allowed = ", ".join(sorted(self._catalogs))
            issues.append(
                f"{location}: unknown catalogId {catalog_id!r} (expected one of {allowed})"
            )
        elif isinstance(surface_id, str):
            surfaces[surface_id] = catalog_id

    def _validate_update_components(
        self, body: dict, location: str, surfaces: dict[str, str], issues: list[str]
    ) -> None:
        self._require_surface(body, location, issues)
        catalog = self._catalog_for_surface(surfaces, body.get("surfaceId"))
        components = body.get("components")
        if not isinstance(components, list) or not components:
            issues.append(f"{location}: components must be a non-empty list")
            return

        ids: set[str] = set()
        parsed: list[tuple[str, str, dict, str]] = []
        for index, component in enumerate(components):
            entry_location = f"{location}.components[{index}]"
            if not isinstance(component, dict):
                issues.append(f"{entry_location}: must be an object")
                continue
            component_id = component.get("id")
            if not isinstance(component_id, str):
                issues.append(f"{entry_location}: id must be a string")
                continue
            if component_id in ids:
                issues.append(f"{entry_location}: duplicate component id {component_id!r}")
            ids.add(component_id)

            component_type = component.get("component")
            if not isinstance(component_type, str):
                issues.append(f"{entry_location}: 'component' must be a component type string")
                continue
            if component_type not in catalog.components:
                issues.append(
                    f"{entry_location}: unknown component {component_type!r} for catalog "
                    f"{catalog.catalog_id!r}"
                )
                continue
            props = {
                key: value for key, value in component.items() if key not in ("id", "component")
            }
            parsed.append((component_id, component_type, props, entry_location))

        for component_id, component_type, props, entry_location in parsed:
            spec = catalog.components[component_type]
            for required in spec.required:
                if required not in props:
                    issues.append(
                        f"{entry_location}.{component_type}: missing required prop {required!r}"
                    )
            for name, token in spec.props.items():
                if name not in props:
                    continue
                if token == "action":
                    issues.extend(self._validate_action(props[name], entry_location, catalog))
                    continue
                problem = _check_prop(token, props[name])
                if problem:
                    issues.append(f"{entry_location}.{component_type}.{name}: {problem}")
            children = props.get("children")
            if isinstance(children, list):
                for child in children:
                    if child not in ids:
                        issues.append(
                            f"{entry_location}.{component_type}: unknown child reference {child!r}"
                        )

    def _validate_action(self, action: Any, location: str, catalog: Catalog) -> list[str]:
        issues: list[str] = []
        if not isinstance(action, dict):
            return [f"{location}.action: must be an object"]
        event = action.get("event")
        if not isinstance(event, dict):
            return [f"{location}.action: must contain an 'event' object"]
        name = event.get("name")
        if name not in catalog.actions:
            issues.append(f"{location}.action.event.name: unknown action {name!r}")
        context = event.get("context", {})
        if not isinstance(context, dict):
            issues.append(f"{location}.action.event.context: must be an object")
        return issues

    def _validate_update_data_model(
        self, body: dict, location: str, surfaces: dict[str, str], issues: list[str]
    ) -> None:
        self._require_surface(body, location, issues)
        if not isinstance(body.get("path"), str):
            issues.append(f"{location}: path must be a JSON Pointer string")

    def _validate_delete_surface(
        self, body: dict, location: str, surfaces: dict[str, str], issues: list[str]
    ) -> None:
        self._require_surface(body, location, issues)
        surface_id = body.get("surfaceId")
        if isinstance(surface_id, str):
            surfaces.pop(surface_id, None)


class JsonschemaValidator:
    """Validate each A2UI message against the A2UI v0.9 schemas."""

    def __init__(self, validator: Any | None = None) -> None:
        self._validator = validator or message_validator()

    def validate(self, messages: Any) -> ValidationResult:
        batch = messages if isinstance(messages, list) else [messages]
        issues: list[str] = []
        for index, message in enumerate(batch):
            errors = sorted(
                self._validator.iter_errors(message),
                key=lambda error: list(error.absolute_path),
            )
            for error in errors:
                path = "/".join(str(part) for part in error.absolute_path)
                location = f"messages[{index}]" + (f"/{path}" if path else "")
                issues.append(f"{location}: {error.message}")
        return ValidationResult(not issues, tuple(issues))


class SdkValidator:
    """Backwards-compatible name; validates via the A2UI SDK schemas + jsonschema."""

    def __init__(self) -> None:
        self._validator = JsonschemaValidator()

    def validate(self, messages: Any) -> ValidationResult:
        return self._validator.validate(messages)


def validate_messages(messages: Sequence[Any], validator: UiValidator | None = None) -> ValidationResult:
    batch = list(messages)
    schema_result = (validator or JsonschemaValidator()).validate(batch)
    if not schema_result.ok:
        return schema_result
    return CatalogValidator().validate(batch)
