from __future__ import annotations

import json
from typing import Any

import anthropic
from anthropic import transform_schema

from app.llm.base import LLMError

MAX_OUTPUT_TOKENS = 8000


class AnthropicProvider:
    def __init__(self, api_key: str, model: str, timeout: float, max_retries: int) -> None:
        # The SDK retries rate limits and 5xx responses with exponential backoff.
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        self.model = model

    def complete_json(
        self, *, system: str, prompt: str, task: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        # `task` only names the job for caching and logs; the API does not need it.
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                # transform_schema adds what the API requires (additionalProperties:
                # false) and moves unsupported bounds such as minimum/maximum into
                # descriptions. Those bounds are still enforced by Pydantic later.
                output_config={
                    "format": {"type": "json_schema", "schema": transform_schema(schema)}
                },
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Model request failed: {exc}") from exc

        if response.stop_reason == "max_tokens":
            raise LLMError("Model response was cut off before it finished.")
        if response.stop_reason == "refusal":
            raise LLMError("Model declined to answer.")
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("Model did not return valid JSON.") from exc
        if not isinstance(result, dict):
            raise LLMError("Model returned JSON that is not an object.")
        return result
