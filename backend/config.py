"""Runtime configuration, loaded from environment variables.

A dependency-free `.env` loader keeps secrets out of tracked files (INV-040).
Nothing in this module ever logs or exposes a value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent

_TRUTHY = {"1", "true", "yes", "on"}


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs into os.environ without overriding existing values."""
    env_path = path or BACKEND_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _as_bool(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in _TRUTHY


def _as_float(name: str, default: str) -> float:
    raw = os.environ.get(name, default).strip()
    try:
        return float(raw)
    except ValueError:
        return float(default)


def _as_int(name: str, default: str) -> int:
    raw = os.environ.get(name, default).strip()
    try:
        return int(raw)
    except ValueError:
        return int(default)


@dataclass(frozen=True)
class Settings:
    database_path: str = "./data/amitie.sqlite3"
    demo_mode: bool = True
    log_level: str = "INFO"

    llm_provider: str = "gemini"
    llm_fallback: str = "deepseek"
    llm_failover_cooldown_seconds: float = 30.0
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_thinking: bool = False

    research_provider: str = "gemini_grounding"
    research_fallback: str = "static_table"
    research_timeout_seconds: float = 8.0

    agent_max_model_calls: int = 6

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=os.environ.get("DATABASE_PATH", "./data/amitie.sqlite3"),
            demo_mode=_as_bool("DEMO_MODE", "1"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
            llm_provider=os.environ.get("LLM_PROVIDER", "gemini").strip().lower(),
            llm_fallback=os.environ.get("LLM_FALLBACK", "deepseek").strip().lower(),
            llm_failover_cooldown_seconds=_as_float("LLM_FAILOVER_COOLDOWN_SECONDS", "30"),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", "").strip(),
            deepseek_base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
            deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip(),
            deepseek_thinking=_as_bool("DEEPSEEK_THINKING", "0"),
            research_provider=os.environ.get("RESEARCH_PROVIDER", "gemini_grounding").strip().lower(),
            research_fallback=os.environ.get("RESEARCH_FALLBACK", "static_table").strip().lower(),
            research_timeout_seconds=_as_float("RESEARCH_TIMEOUT_SECONDS", "8"),
            agent_max_model_calls=_as_int("AGENT_MAX_MODEL_CALLS", "6"),
        )
