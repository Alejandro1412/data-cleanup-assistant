from __future__ import annotations

from typing import Any

import anthropic

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
        self, *, system: str, prompt: str, tool_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                tools=[
                    {
                        "name": tool_name,
                        "description": "Return the result in this exact structure.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Model request failed: {exc}") from exc

        if response.stop_reason == "max_tokens":
            raise LLMError("Model response was cut off before it finished.")
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return dict(block.input)
        raise LLMError("Model did not return structured output.")
