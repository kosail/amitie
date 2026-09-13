"""Central structured logging configuration with structlog (INV-018, AGENTS.md §6)."""

from __future__ import annotations

import logging
import sys
from typing import Any, MutableMapping

import structlog

# Field names that must NEVER appear in logs (AGENTS.md §8).
_FORBIDDEN_KEYS = {
    "api_key",
    "gemini_api_key",
    "deepseek_api_key",
    "elevenlabs_api_key",
    "password",
    "audio",
    "audio_bytes",
    "raw_audio",
    "financial_payload",
}


def _redact_sensitive_fields(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Last-line-of-defense structlog processor to redact forbidden fields."""
    for key in list(event_dict):
        if key.lower() in _FORBIDDEN_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(env: str = "development", level: str = "INFO") -> None:
    """Configure structlog and standard logging for the backend.

    env: "development" | "production"
    level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL"
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        _redact_sensitive_fields,
    ]

    is_prod = str(env).strip().lower() == "production"
    renderer = (
        structlog.processors.JSONRenderer()
        if is_prod
        else structlog.dev.ConsoleRenderer(colors=True if sys.stdout.isatty() else False)
    )

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    log_level = getattr(logging, str(level).strip().upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)
