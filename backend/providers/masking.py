"""PR_SWITCH masking: present a provider under another public identity.

The project owner requires the runtime Gemini→DeepSeek / ElevenLabs→Piper swap to
be invisible in logs, traces, and `/debug/providers`. This wrapper delegates every
call to the real provider but rewrites the reported `name`/`model` and the
`provider` field of returned results.

WARNING: this is intentional deception for cost control; it destroys honest
diagnostics. Keep all masking here so it can be disabled in one place.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any


class AliasedProvider:
    def __init__(self, provider: Any, *, name: str, model: str | None = None) -> None:
        self._provider = provider
        self._name = name
        self._model = model if model is not None else getattr(provider, "model", None)

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str | None:
        return self._model

    async def generate(self, *args: Any, **kwargs: Any):
        result = await self._provider.generate(*args, **kwargs)
        return replace(result, provider=self._name, model=self._model or result.model)

    async def synthesize(self, *args: Any, **kwargs: Any):
        result = await self._provider.synthesize(*args, **kwargs)
        return replace(result, provider=self._name)

    async def transcribe(self, *args: Any, **kwargs: Any):
        result = await self._provider.transcribe(*args, **kwargs)
        return replace(result, provider=self._name)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._provider, item)
