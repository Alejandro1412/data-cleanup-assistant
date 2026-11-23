from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from app.detectors import DetectionContext
from app.pipeline.profile import profile_frame

Handler = Callable[[str], dict[str, Any]]


class FakeProvider:
    """Returns canned answers per tool name and records every prompt."""

    model = "fake-model"

    def __init__(self, responses: dict[str, dict[str, Any] | Handler | Exception]) -> None:
        self.responses = responses
        self.prompts: dict[str, list[str]] = {}

    def complete_json(
        self, *, system: str, prompt: str, task: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        self.prompts.setdefault(task, []).append(prompt)
        response = self.responses.get(task)
        if response is None:
            return {"changes": [], "decisions": [], "issues": []}
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(prompt)
        return response


def frame_from(rows: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, dtype=object)


def context_for(frame: pd.DataFrame) -> DetectionContext:
    return DetectionContext(frame, profile_frame(frame))
