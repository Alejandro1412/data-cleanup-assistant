from __future__ import annotations

from typing import Any, Protocol


class LLMError(Exception):
    """Raised when the model call fails or returns something unusable."""


class LLMProvider(Protocol):
    """The only thing the rest of the app knows about the model.

    Implementations return a JSON object that follows `schema`. The Anthropic
    adapter gets it through structured outputs, so the API itself constrains
    the response to the schema.
    """

    model: str

    def complete_json(
        self, *, system: str, prompt: str, task: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...
