"""Runs the full analysis: profile, rule-based detectors, then the AI passes.

Each AI pass is optional and isolated. If the model is not configured, times
out or returns something invalid, that pass is skipped with a warning and the
rule-based results are still returned.
"""

from __future__ import annotations

import logging
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from app.config import Settings
from app.detectors import DetectionContext, default_detectors
from app.detectors.categories import (
    CategoryMapping,
    build_category_suggestions,
    column_value_counts,
    rule_based_mapping,
)
from app.domain.models import (
    Action,
    ColumnProfile,
    ColumnType,
    IssueKind,
    Source,
    Suggestion,
)
from app.llm.base import LLMError
from app.llm.reviewer import AIReviewer
from app.pipeline.profile import profile_frame

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]
# A model verdict of "not a duplicate" this confident removes the rule's suggestion.
DISMISS_DUPLICATE_CONFIDENCE = 0.6
SAMPLE_SEED = 7


@dataclass
class AnalysisResult:
    profiles: dict[str, ColumnProfile]
    suggestions: list[Suggestion]
    warnings: list[str] = field(default_factory=list)


def _noop(_: str) -> None:
    return None


class Analyzer:
    def __init__(self, settings: Settings, reviewer: AIReviewer | None) -> None:
        self._settings = settings
        self._reviewer = reviewer

    def run(self, frame: pd.DataFrame, progress: ProgressCallback = _noop) -> AnalysisResult:
        progress("Profiling columns")
        profiles = profile_frame(frame)
        context = DetectionContext(frame, profiles, self._settings.default_phone_region)

        suggestions: list[Suggestion] = []
        for detector in sorted(default_detectors(), key=lambda d: d.stage):
            progress(f"Running check: {detector.name.replace('_', ' ')}")
            suggestions.extend(detector.detect(context))

        warnings: list[str] = []
        if self._reviewer is None:
            warnings.append(
                "AI review is off because no API key is configured. Only rule-based checks ran."
            )
        else:
            suggestions = self._ai_passes(context, suggestions, warnings, progress)

        progress("Preparing suggestions")
        merged = merge_suggestions(suggestions)
        for suggestion in merged:
            suggestion.id = uuid.uuid4().hex[:12]
        merged.sort(key=lambda s: (s.row_index, s.column or ""))
        return AnalysisResult(profiles=profiles, suggestions=merged, warnings=warnings)

    def _ai_passes(
        self,
        context: DetectionContext,
        suggestions: list[Suggestion],
        warnings: list[str],
        progress: ProgressCallback,
    ) -> list[Suggestion]:
        passes: list[tuple[str, Callable[[DetectionContext, list[Suggestion]], list[Suggestion]]]]
        passes = [
            ("Asking AI to match category variants", self._ai_categories),
            ("Asking AI to confirm possible duplicates", self._ai_duplicates),
            ("Asking AI to review records", self._ai_records),
        ]
        for message, ai_pass in passes:
            progress(message)
            try:
                suggestions = ai_pass(context, suggestions)
            except LLMError as exc:
                logger.warning("AI pass failed: %s", exc)
                warnings.append(
                    f"{message.removeprefix('Asking AI to ').capitalize()} was skipped: {exc}"
                )
        return suggestions

    def _ai_categories(
        self, context: DetectionContext, suggestions: list[Suggestion]
    ) -> list[Suggestion]:
        assert self._reviewer is not None
        limit = self._settings.llm_max_distinct_values
        columns = [
            c
            for c in context.columns_of(ColumnType.CATEGORICAL)
            if 1 < context.profiles[c].distinct_count <= limit
        ][: self._settings.llm_max_categorical_columns]

        for column in columns:
            counts = column_value_counts(context, column)
            mapping: dict[str, CategoryMapping] = rule_based_mapping(counts)
            for change in self._reviewer.normalize_categories(column, counts):
                mapping[change.value] = CategoryMapping(
                    canonical=change.canonical,
                    confidence=round(change.confidence, 2),
                    reason=change.reason,
                    source=Source.AI,
                )
            suggestions = [
                s
                for s in suggestions
                if not (s.kind is IssueKind.INCONSISTENT_CATEGORY and s.column == column)
            ]
            suggestions.extend(build_category_suggestions(context, column, mapping))
        return suggestions

    def _ai_duplicates(
        self, context: DetectionContext, suggestions: list[Suggestion]
    ) -> list[Suggestion]:
        assert self._reviewer is not None
        candidates = [s for s in suggestions if s.kind is IssueKind.NEAR_DUPLICATE]
        candidates = candidates[: self._settings.llm_max_duplicate_pairs]
        if not candidates:
            return suggestions

        columns = [
            name
            for name, p in context.profiles.items()
            if p.inferred_type is not ColumnType.IDENTIFIER
        ]

        def row(index: int) -> dict[str, str]:
            return {c: str(context.frame.at[index, c]) for c in columns}

        by_pair = {f"p{i}": s for i, s in enumerate(candidates)}
        pairs = {
            pair_id: (row(s.related_row_index or 0), row(s.row_index))
            for pair_id, s in by_pair.items()
        }
        dismissed: set[int] = set()
        for decision in self._reviewer.adjudicate_duplicates(pairs):
            suggestion = by_pair[decision.pair_id]
            if not decision.is_duplicate:
                if decision.confidence >= DISMISS_DUPLICATE_CONFIDENCE:
                    dismissed.add(id(suggestion))
                continue
            suggestion.source = Source.AI
            suggestion.confidence = round(decision.confidence, 2)
            suggestion.reason = (
                f"{decision.reason} Matches row {(suggestion.related_row_index or 0) + 1}."
            )
        return [s for s in suggestions if id(s) not in dismissed]

    def _ai_records(
        self, context: DetectionContext, suggestions: list[Suggestion]
    ) -> list[Suggestion]:
        assert self._reviewer is not None
        limit = self._settings.llm_max_review_rows
        flagged = sorted(
            {
                s.row_index
                for s in suggestions
                if s.kind in (IssueKind.OUTLIER, IssueKind.INVALID_VALUE)
            }
        )[: limit // 2]
        remaining = [i for i in range(len(context.frame)) if i not in set(flagged)]
        sample_size = min(len(remaining), limit - len(flagged))
        sampled = random.Random(SAMPLE_SEED).sample(remaining, sample_size)
        selected = sorted(flagged + sampled)
        if not selected:
            return suggestions

        columns = [
            {
                "name": p.name,
                "type": p.inferred_type.value,
                "examples": p.sample_values[:5],
            }
            for p in context.profiles.values()
        ]
        rows = {
            i + 1: {str(c): str(context.frame.at[i, c]) for c in context.frame.columns}
            for i in selected
        }
        taken_cells = {s.cell_key for s in suggestions if s.cell_key}
        for issue in self._reviewer.review_records(columns, rows):
            row_index = issue.row - 1
            if issue.column and (row_index, issue.column) in taken_cells:
                continue
            has_fix = issue.column is not None and issue.proposed_value is not None
            suggestions.append(
                Suggestion(
                    kind=IssueKind.SUSPICIOUS_RECORD,
                    action=Action.SET_VALUE if has_fix else Action.FLAG,
                    row_index=row_index,
                    column=issue.column,
                    current_value=(
                        str(context.frame.at[row_index, issue.column]) if issue.column else None
                    ),
                    proposed_value=issue.proposed_value if has_fix else None,
                    reason=issue.problem,
                    confidence=round(issue.confidence, 2),
                    source=Source.AI,
                    group_key=f"suspicious:{issue.column or 'row'}",
                )
            )
        return suggestions


def merge_suggestions(suggestions: list[Suggestion]) -> list[Suggestion]:
    """Keep at most one value change per cell and one row drop per row.

    Input is in detector stage order, so a later SET_VALUE on the same cell
    replaces an earlier one. Flags never change data and are always kept.
    """
    value_changes: dict[tuple[int, str], Suggestion] = {}
    drops: dict[int, Suggestion] = {}
    flags: list[Suggestion] = []
    for suggestion in suggestions:
        if suggestion.action is Action.DROP_ROW:
            current = drops.get(suggestion.row_index)
            if current is None or suggestion.confidence > current.confidence:
                drops[suggestion.row_index] = suggestion
        elif suggestion.action is Action.SET_VALUE and suggestion.cell_key:
            value_changes[suggestion.cell_key] = suggestion
        else:
            flags.append(suggestion)
    return [*value_changes.values(), *drops.values(), *flags]
