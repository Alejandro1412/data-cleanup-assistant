from __future__ import annotations

from typing import Any, Protocol


class LLMError(Exception):
    """Raised when the model call fails or returns something unusable."""


class LLMProvider(Protocol):
    """The only thing the rest of the app knows about the model.

    Implementations must return the arguments of a forced tool call, which is
    how structured output is obtained: the model has to answer by "calling" a
    tool whose input schema is the response schema.
    """

    model: str

    def complete_json(
        self, *, system: str, prompt: str, tool_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...
