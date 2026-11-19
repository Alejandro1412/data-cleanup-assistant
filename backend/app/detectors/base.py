from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from app.domain.models import ColumnProfile, ColumnType, Suggestion


@dataclass(frozen=True)
class DetectionContext:
    frame: pd.DataFrame
    profiles: dict[str, ColumnProfile]
    phone_region: str = "US"

    def columns_of(self, *types: ColumnType) -> list[str]:
        return [name for name, p in self.profiles.items() if p.inferred_type in types]

    def cells(self, column: str) -> list[tuple[int, str]]:
        return [(position, str(value)) for position, value in enumerate(self.frame[column])]


class Detector(Protocol):
    """A single, independent data quality check.

    `stage` orders detectors. When two detectors propose a new value for the
    same cell, the later stage wins, because later stages work on values the
    earlier ones have already normalized (a category mapping already has its
    whitespace trimmed, for example).
    """

    name: str
    stage: int

    def detect(self, context: DetectionContext) -> list[Suggestion]: ...
