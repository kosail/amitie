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
from .registry import build_llm, build_llm_gateway, build_research
from .research import (
    FallbackResearch,
    GeminiGroundingResearch,
    ResearchProvider,
    ResearchSnapshot,
    StaticPriceTableResearch,
)

__all__ = [
    "ChatMessage",
    "FallbackLLM",
    "FallbackResearch",
    "GeminiGroundingResearch",
    "LLMProvider",
    "LLMResult",
    "ProviderError",
    "ProviderResponseError",
    "ProviderUnavailableError",
    "ResearchProvider",
    "ResearchSnapshot",
    "StaticPriceTableResearch",
    "ToolCall",
    "ToolSpec",
    "Usage",
    "build_llm",
    "build_llm_gateway",
    "build_research",
]
