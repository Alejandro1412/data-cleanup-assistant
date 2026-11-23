from types import SimpleNamespace
from typing import Any

import pytest

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMError

SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "number", "minimum": 0, "maximum": 1}},
    "required": ["score"],
}


def _provider(text: str, stop_reason: str = "end_turn") -> tuple[AnthropicProvider, dict[str, Any]]:
    provider = AnthropicProvider(api_key="test", model="test-model", timeout=5, max_retries=0)
    sent: dict[str, Any] = {}

    def create(**kwargs: Any) -> SimpleNamespace:
        sent.update(kwargs)
        return SimpleNamespace(
            stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)]
        )

    provider._client = SimpleNamespace(messages=SimpleNamespace(create=create))  # type: ignore[assignment]
    return provider, sent


def test_requests_structured_output_and_parses_the_json() -> None:
    provider, sent = _provider('{"score": 0.9}')

    result = provider.complete_json(system="s", prompt="p", task="t", schema=SCHEMA)

    assert result == {"score": 0.9}
    schema = sent["output_config"]["format"]["schema"]
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert schema["additionalProperties"] is False
    assert "minimum" not in schema["properties"]["score"]
    assert "tool_choice" not in sent


@pytest.mark.parametrize(
    ("text", "stop_reason", "message"),
    [
        ("not json", "end_turn", "valid JSON"),
        ("[1, 2]", "end_turn", "not an object"),
        ('{"score": 0.', "max_tokens", "cut off"),
        ("", "refusal", "declined"),
    ],
)
def test_unusable_responses_raise(text: str, stop_reason: str, message: str) -> None:
    provider, _ = _provider(text, stop_reason)

    with pytest.raises(LLMError, match=message):
        provider.complete_json(system="s", prompt="p", task="t", schema=SCHEMA)
