"""Core domain types.

A Suggestion is a proposed patch against the original file. The original data is
never modified; the cleaned output is produced by replaying accepted patches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IssueKind(StrEnum):
    MISSING_VALUE = "missing_value"
    EXACT_DUPLICATE = "exact_duplicate"
    NEAR_DUPLICATE = "near_duplicate"
    INCONSISTENT_FORMAT = "inconsistent_format"
    INCONSISTENT_CATEGORY = "inconsistent_category"
    INVALID_VALUE = "invalid_value"
    OUTLIER = "outlier"
    SUSPICIOUS_RECORD = "suspicious_record"


class Action(StrEnum):
    SET_VALUE = "set_value"
    DROP_ROW = "drop_row"
    # No automatic change. The reviewer can acknowledge it or type a value.
    FLAG = "flag"


class Source(StrEnum):
    RULE = "rule"
    AI = "ai"


class Status(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class DatasetStatus(StrEnum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class ColumnType(StrEnum):
    IDENTIFIER = "identifier"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    EMAIL = "email"
    PHONE = "phone"
    CATEGORICAL = "categorical"
    TEXT = "text"
    EMPTY = "empty"


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    inferred_type: ColumnType
    non_null_count: int
    null_count: int
    distinct_count: int
    # Share of non-null values that parse as the inferred type.
    type_confidence: float
    sample_values: list[str]
    top_values: list[tuple[str, int]] = field(default_factory=list)
    numeric_summary: dict[str, float] | None = None

    @property
    def null_ratio(self) -> float:
        total = self.non_null_count + self.null_count
        return self.null_count / total if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "inferred_type": self.inferred_type.value,
            "non_null_count": self.non_null_count,
            "null_count": self.null_count,
            "null_ratio": round(self.null_ratio, 4),
            "distinct_count": self.distinct_count,
            "type_confidence": round(self.type_confidence, 4),
            "sample_values": self.sample_values,
            "top_values": [[v, c] for v, c in self.top_values],
            "numeric_summary": self.numeric_summary,
        }


@dataclass
class Suggestion:
    kind: IssueKind
    action: Action
    row_index: int
    reason: str
    confidence: float
    source: Source
    group_key: str
    column: str | None = None
    current_value: str | None = None
    proposed_value: str | None = None
    # Extra context for the reviewer, e.g. the row a duplicate matches.
    related_row_index: int | None = None
    id: str = ""
    status: Status = Status.PENDING
    # Set when the reviewer overrides the proposed value.
    final_value: str | None = None

    @property
    def effective_value(self) -> str | None:
        return self.final_value if self.final_value is not None else self.proposed_value

    @property
    def cell_key(self) -> tuple[int, str] | None:
        if self.action is Action.DROP_ROW or self.column is None:
            return None
        return (self.row_index, self.column)
