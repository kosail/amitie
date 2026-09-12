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
from .registry import build_llm, build_llm_gateway, build_research, build_stt, build_tts
from .research import (
    FallbackResearch,
    GeminiGroundingResearch,
    ResearchProvider,
    ResearchSnapshot,
    StaticPriceTableResearch,
)
from .voice import (
    EdgeTTS,
    ElevenLabsTTS,
    FallbackSTT,
    FallbackTTS,
    FasterWhisperSTT,
    GeminiSTT,
    NullSTT,
    NullTTS,
    STTProvider,
    SynthesisResult,
    TranscriptionResult,
    TTSProvider,
)

__all__ = [
    "ChatMessage",
    "EdgeTTS",
    "ElevenLabsTTS",
    "FallbackLLM",
    "FallbackResearch",
    "FallbackSTT",
    "FallbackTTS",
    "FasterWhisperSTT",
    "GeminiGroundingResearch",
    "GeminiSTT",
    "LLMProvider",
    "LLMResult",
    "NullSTT",
    "NullTTS",
    "ProviderError",
    "ProviderResponseError",
    "ProviderUnavailableError",
    "ResearchProvider",
    "ResearchSnapshot",
    "STTProvider",
    "StaticPriceTableResearch",
    "SynthesisResult",
    "TTSProvider",
    "ToolCall",
    "ToolSpec",
    "TranscriptionResult",
    "Usage",
    "build_llm",
    "build_llm_gateway",
    "build_research",
    "build_stt",
    "build_tts",
]
