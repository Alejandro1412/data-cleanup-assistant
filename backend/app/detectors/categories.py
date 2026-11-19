"""Spelling variants inside categorical columns ("CA", "ca", "Calif.").

The rule-based pass catches case, punctuation and typo variants. Variants that
need world knowledge ("USA" vs "United States") are left to the AI pass, which
produces a mapping in the same shape so both share `build_category_suggestions`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.detectors.base import DetectionContext
from app.domain.models import Action, ColumnType, IssueKind, Source, Suggestion
from app.pipeline import values as v

FUZZY_THRESHOLD = 90
MIN_FUZZY_LENGTH = 5
# A "variant" should be rare compared to the value it is merged into. Two large
# groups with similar names are more likely two real categories.
MAX_VARIANT_SHARE = 0.1


@dataclass(frozen=True)
class CategoryMapping:
    canonical: str
    confidence: float
    reason: str
    source: Source


def rule_based_mapping(values: Counter[str]) -> dict[str, CategoryMapping]:
    by_key: dict[str, Counter[str]] = defaultdict(Counter)
    for value, count in values.items():
        by_key[v.normalize_key(value)][value] += count

    ordered_keys = sorted(by_key, key=lambda k: -sum(by_key[k].values()))
    representative: dict[str, str] = {}
    for key in ordered_keys:
        size = sum(by_key[key].values())
        match = None
        for rep in dict.fromkeys(representative.values()):
            rep_size = sum(by_key[rep].values())
            if (
                len(key) >= MIN_FUZZY_LENGTH
                and len(rep) >= MIN_FUZZY_LENGTH
                and size <= max(2, rep_size * MAX_VARIANT_SHARE)
                and fuzz.ratio(key, rep) >= FUZZY_THRESHOLD
            ):
                match = rep
                break
        representative[key] = match or key

    clusters: dict[str, Counter[str]] = defaultdict(Counter)
    for key, rep in representative.items():
        clusters[rep].update(by_key[key])

    mapping: dict[str, CategoryMapping] = {}
    for members in clusters.values():
        if len(members) < 2:
            continue
        canonical, canonical_count = max(members.items(), key=lambda item: (item[1], len(item[0])))
        for value in members:
            if value == canonical:
                continue
            # Same key means only case or punctuation differ; otherwise it was a fuzzy match.
            only_case_or_punctuation = v.normalize_key(value) == v.normalize_key(canonical)
            mapping[value] = CategoryMapping(
                canonical=canonical,
                confidence=0.9 if only_case_or_punctuation else 0.75,
                reason=(
                    f'"{value}" looks like a different spelling of "{canonical}", '
                    f"which {canonical_count} rows use."
                ),
                source=Source.RULE,
            )
    return mapping


def column_value_counts(context: DetectionContext, column: str) -> Counter[str]:
    return Counter(value.strip() for _, value in context.cells(column) if not v.is_null(value))


def build_category_suggestions(
    context: DetectionContext, column: str, mapping: dict[str, CategoryMapping]
) -> list[Suggestion]:
    suggestions = []
    for row, value in context.cells(column):
        trimmed = value.strip()
        entry = mapping.get(trimmed)
        if entry is None or entry.canonical == trimmed:
            continue
        suggestions.append(
            Suggestion(
                kind=IssueKind.INCONSISTENT_CATEGORY,
                action=Action.SET_VALUE,
                row_index=row,
                column=column,
                current_value=value,
                proposed_value=entry.canonical,
                reason=entry.reason,
                confidence=entry.confidence,
                source=entry.source,
                group_key=f"category:{column}:{trimmed}",
            )
        )
    return suggestions


class CategoryDetector:
    name = "categories"
    stage = 30

    def detect(self, context: DetectionContext) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for column in context.columns_of(ColumnType.CATEGORICAL):
            mapping = rule_based_mapping(column_value_counts(context, column))
            suggestions.extend(build_category_suggestions(context, column, mapping))
        return suggestions
