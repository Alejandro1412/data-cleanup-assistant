"""Builds the cleaned file by replaying accepted suggestions on the original."""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass

import pandas as pd

from app.domain.models import Action, Status, Suggestion


@dataclass(frozen=True)
class AuditEntry:
    suggestion_id: str
    row: int
    column: str
    action: str
    before: str
    after: str
    issue: str
    source: str
    reason: str


def apply_suggestions(
    original: pd.DataFrame, suggestions: list[Suggestion]
) -> tuple[pd.DataFrame, list[AuditEntry]]:
    accepted = [s for s in suggestions if s.status is Status.ACCEPTED]
    cleaned = original.copy()
    audit: list[AuditEntry] = []

    # A flag the reviewer typed a value into becomes a value change. Those come
    # last so a typed value wins over an automatic one on the same cell.
    changes = [s for s in accepted if s.action is Action.SET_VALUE]
    changes += [s for s in accepted if s.action is Action.FLAG and s.final_value is not None]

    for suggestion in changes:
        if suggestion.column is None or suggestion.column not in cleaned.columns:
            continue
        before = str(cleaned.at[suggestion.row_index, suggestion.column])
        after = suggestion.effective_value or ""
        if before == after:
            continue
        cleaned.at[suggestion.row_index, suggestion.column] = after
        audit.append(_entry(suggestion, suggestion.column, before, after))

    drops = sorted({s.row_index for s in accepted if s.action is Action.DROP_ROW})
    for suggestion in (s for s in accepted if s.action is Action.DROP_ROW):
        audit.append(_entry(suggestion, "", "", ""))
    cleaned = cleaned.drop(index=drops).reset_index(drop=True)
    return cleaned, audit


def _entry(suggestion: Suggestion, column: str, before: str, after: str) -> AuditEntry:
    return AuditEntry(
        suggestion_id=suggestion.id,
        row=suggestion.row_index + 1,
        column=column,
        action=suggestion.action.value,
        before=before,
        after=after,
        issue=suggestion.kind.value,
        source=suggestion.source.value,
        reason=suggestion.reason,
    )


def to_csv_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def audit_to_csv_bytes(entries: list[AuditEntry]) -> bytes:
    columns = list(AuditEntry.__dataclass_fields__)
    frame = pd.DataFrame([asdict(e) for e in entries], columns=columns)
    return to_csv_bytes(frame)
