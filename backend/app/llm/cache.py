from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from app.llm.base import LLMProvider


class CacheStore(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any]) -> None: ...


class CachedProvider:
    """Re-analyzing the same file (or one that shares columns) costs nothing.

    Responses are keyed by model, prompt and schema. Caching also makes repeat
    runs deterministic, which matters for a review tool: the same file should
    not produce a different set of suggestions every time it is uploaded.
    """

    def __init__(self, inner: LLMProvider, store: CacheStore) -> None:
        self._inner = inner
        self._store = store
        self.model = inner.model

    def complete_json(
        self, *, system: str, prompt: str, tool_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        payload = json.dumps(
            {"model": self.model, "system": system, "prompt": prompt, "schema": schema},
            sort_keys=True,
        )
        key = hashlib.sha256(payload.encode()).hexdigest()
        cached = self._store.get(key)
        if cached is not None:
            return cached
        result = self._inner.complete_json(
            system=system, prompt=prompt, tool_name=tool_name, schema=schema
        )
        self._store.set(key, result)
        return result
