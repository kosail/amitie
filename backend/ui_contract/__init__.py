"""Machine-readable A2UI catalog, prompt generation, and validation."""

from .catalog import CATALOG, CATALOG_ID, Catalog, ComponentSpec, load_catalog
from .prompt import build_system_prompt, catalog_summary, describe_components
from .validator import (
    A2uiValidationError,
    CatalogValidator,
    JsonschemaValidator,
    SdkValidator,
    UiValidator,
    ValidationResult,
    validate_messages,
)

__all__ = [
    "A2uiValidationError",
    "CATALOG",
    "CATALOG_ID",
    "Catalog",
    "CatalogValidator",
    "ComponentSpec",
    "JsonschemaValidator",
    "SdkValidator",
    "UiValidator",
    "ValidationResult",
    "build_system_prompt",
    "catalog_summary",
    "describe_components",
    "load_catalog",
    "validate_messages",
]
