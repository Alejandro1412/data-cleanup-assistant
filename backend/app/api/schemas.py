from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.domain.models import Action, DatasetStatus, IssueKind, Source, Status, Suggestion
from app.storage.repository import DatasetRecord


class DatasetSummary(BaseModel):
    id: str
    filename: str
    created_at: str
    status: DatasetStatus
    progress: str | None
    error: str | None
    row_count: int

    @classmethod
    def from_record(cls, record: DatasetRecord) -> DatasetSummary:
        return cls(
            id=record.id,
            filename=record.filename,
            created_at=record.created_at,
            status=record.status,
            progress=record.progress,
            error=record.error,
            row_count=record.row_count,
        )


class DatasetDetail(DatasetSummary):
    columns: list[str]
    profile: list[dict[str, Any]]
    warnings: list[str]
    ai_model: str | None
    delimiter: str | None
    encoding: str | None

    @classmethod
    def from_record(cls, record: DatasetRecord) -> DatasetDetail:
        return cls(
            **DatasetSummary.from_record(record).model_dump(),
            columns=record.columns,
            profile=record.profile,
            warnings=record.warnings,
            ai_model=record.ai_model,
            delimiter=record.delimiter,
            encoding=record.encoding,
        )


class SuggestionOut(BaseModel):
    id: str
    kind: IssueKind
    action: Action
    row_index: int
    column: str | None
    current_value: str | None
    proposed_value: str | None
    final_value: str | None
    related_row_index: int | None
    reason: str
    confidence: float
    source: Source
    group_key: str
    status: Status

    @classmethod
    def from_domain(cls, s: Suggestion) -> SuggestionOut:
        return cls(
            id=s.id,
            kind=s.kind,
            action=s.action,
            row_index=s.row_index,
            column=s.column,
            current_value=s.current_value,
            proposed_value=s.proposed_value,
            final_value=s.final_value,
            related_row_index=s.related_row_index,
            reason=s.reason,
            confidence=s.confidence,
            source=s.source,
            group_key=s.group_key,
            status=s.status,
        )


class ReviewRequest(BaseModel):
    status: Status
    final_value: str | None = Field(
        default=None, description="Replaces the proposed value. Only valid when accepting."
    )


class BulkReviewRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=50_000)
    status: Status


class RowsPage(BaseModel):
    columns: list[str]
    total: int
    offset: int
    rows: list[dict[str, Any]]


class HealthOut(BaseModel):
    status: str
    ai_enabled: bool
