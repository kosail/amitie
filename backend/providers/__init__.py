"""Provider layer (INV-012, INV-013).

`gemini` and `deepseek` adapters are imported lazily inside the registry so the
package (and its tests) do not require every vendor SDK to be installed.
"""

from .base import (
    ChatMessage,
    LLMProvider,
    LLMResult,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    ToolCall,
    ToolSpec,
    Usage,
)
from .gateway import FallbackLLM
from .registry import build_llm, build_llm_gateway

__all__ = [
    "ChatMessage",
    "FallbackLLM",
    "LLMProvider",
    "LLMResult",
    "ProviderError",
    "ProviderResponseError",
    "ProviderUnavailableError",
    "ToolCall",
    "ToolSpec",
    "Usage",
    "build_llm",
    "build_llm_gateway",
]
