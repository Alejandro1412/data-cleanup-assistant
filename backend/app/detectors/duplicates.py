"""Exact and near-duplicate rows.

Comparing every pair of rows field by field is O(n^2) in Python and too slow
past a few thousand rows. Instead, candidate pairs come from two cheap sources:

* a vectorized whole-row similarity matrix (rapidfuzz `cdist`, C++), used for
  files up to `MATRIX_MAX_ROWS`, or a sorted-neighbourhood window beyond that;
* rows sharing a strong key such as the same email or phone number.

Only those candidates get the slower per-column scoring.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from rapidfuzz import fuzz, process

from app.detectors.base import DetectionContext
from app.domain.models import Action, ColumnType, IssueKind, Source, Suggestion
from app.pipeline import values as v

MATRIX_MAX_ROWS = 3000
NEIGHBOURHOOD_WINDOW = 10
CANDIDATE_CUTOFF = 75
NEAR_DUPLICATE_THRESHOLD = 85
STRONG_KEY_TYPES = (ColumnType.EMAIL, ColumnType.PHONE)
HIGH_WEIGHT_TYPES = (ColumnType.TEXT, ColumnType.EMAIL, ColumnType.PHONE)
MAX_LISTED_DIFFERENCES = 4


@dataclass(frozen=True)
class DuplicatePair:
    keep: int
    drop: int
    score: float
    differences: list[tuple[str, str, str]]


def _canonical(value: str, column_type: ColumnType, date_order: str | None) -> str:
    if v.is_null(value):
        return ""
    if column_type is ColumnType.DATE:
        fmt = v.resolve_date_format(value, date_order)
        if fmt:
            return datetime.strptime(value.strip(), fmt).strftime(v.ISO_DATE)
    if column_type is ColumnType.PHONE:
        digits = "".join(ch for ch in value if ch.isdigit())
        return digits[-10:]
    if column_type in (ColumnType.INTEGER, ColumnType.FLOAT):
        number = v.parse_number(value)
        if number is not None:
            return v.format_number(number)
    if column_type is ColumnType.EMAIL:
        return value.strip().lower()
    if column_type is ColumnType.BOOLEAN:
        parsed = v.boolean_value(value)
        if parsed is not None:
            return "true" if parsed else "false"
    return v.normalize_key(value)


class DuplicateDetector:
    name = "duplicates"
    stage = 50

    def detect(self, context: DetectionContext) -> list[Suggestion]:
        columns = [
            name
            for name, profile in context.profiles.items()
            if profile.inferred_type not in (ColumnType.IDENTIFIER, ColumnType.EMPTY)
        ]
        if not columns:
            return []

        types = {c: context.profiles[c].inferred_type for c in columns}
        orders = {
            c: v.pick_date_format([str(x) for x in context.frame[c].tolist()])
            for c in columns
            if types[c] is ColumnType.DATE
        }
        rows: list[list[str]] = [
            [_canonical(str(record[c]), types[c], orders.get(c)) for c in columns]
            for record in context.frame[columns].to_dict("records")
        ]

        suggestions, exact_dropped = self._exact(context, columns, rows)
        pairs = self.near_duplicate_pairs(context, columns, rows, types, exclude=exact_dropped)
        suggestions.extend(self._near_suggestion(context, pair) for pair in pairs)
        return suggestions

    def _exact(
        self, context: DetectionContext, columns: list[str], rows: list[list[str]]
    ) -> tuple[list[Suggestion], set[int]]:
        first_seen: dict[tuple[str, ...], int] = {}
        suggestions: list[Suggestion] = []
        dropped: set[int] = set()
        for index, row in enumerate(rows):
            if not any(row):
                continue
            key = tuple(row)
            if key not in first_seen:
                first_seen[key] = index
                continue
            original = first_seen[key]
            dropped.add(index)
            raw_identical = all(
                str(context.frame.at[index, c]) == str(context.frame.at[original, c])
                for c in columns
            )
            if raw_identical:
                reason = f"Same values as row {original + 1} in every column"
                reason += " except the ID." if len(columns) < len(context.frame.columns) else "."
            else:
                reason = (
                    f"Same record as row {original + 1} once differences in case, spacing "
                    "and date, number or phone formatting are ignored."
                )
            suggestions.append(
                Suggestion(
                    kind=IssueKind.EXACT_DUPLICATE,
                    action=Action.DROP_ROW,
                    row_index=index,
                    related_row_index=original,
                    reason=reason,
                    confidence=0.98,
                    source=Source.RULE,
                    group_key="exact_duplicate",
                )
            )
        return suggestions, dropped

    def near_duplicate_pairs(
        self,
        context: DetectionContext,
        columns: list[str],
        rows: list[list[str]],
        types: dict[str, ColumnType],
        exclude: set[int],
    ) -> list[DuplicatePair]:
        candidates = self._candidates(columns, rows, types, exclude)
        weights = [2.0 if types[c] in HIGH_WEIGHT_TYPES else 1.0 for c in columns]

        best_for_row: dict[int, DuplicatePair] = {}
        for a, b in candidates:
            score = self._pair_score(rows[a], rows[b], weights)
            if score < NEAR_DUPLICATE_THRESHOLD or rows[a] == rows[b]:
                continue
            keep, drop = self._choose_keeper(rows, a, b)
            differences = [
                (column, str(context.frame.at[keep, column]), str(context.frame.at[drop, column]))
                for column, x, y in zip(columns, rows[keep], rows[drop], strict=True)
                if x != y
            ]
            pair = DuplicatePair(keep, drop, round(score, 1), differences)
            current = best_for_row.get(drop)
            if current is None or pair.score > current.score:
                best_for_row[drop] = pair
        return sorted(best_for_row.values(), key=lambda p: p.drop)

    def _candidates(
        self,
        columns: list[str],
        rows: list[list[str]],
        types: dict[str, ColumnType],
        exclude: set[int],
    ) -> set[tuple[int, int]]:
        active = [i for i, row in enumerate(rows) if i not in exclude and any(row)]
        joined = [" ".join(rows[i]) for i in active]
        pairs: set[tuple[int, int]] = set()

        if len(active) <= MATRIX_MAX_ROWS:
            matrix = process.cdist(
                joined,
                joined,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=CANDIDATE_CUTOFF,
                dtype=np.uint8,
                workers=-1,
            )
            for x, y in zip(*np.nonzero(np.triu(matrix, k=1)), strict=True):
                pairs.add((active[int(x)], active[int(y)]))
        else:
            order = sorted(range(len(active)), key=lambda i: joined[i])
            for pos, i in enumerate(order):
                for j in order[pos + 1 : pos + 1 + NEIGHBOURHOOD_WINDOW]:
                    if fuzz.token_sort_ratio(joined[i], joined[j]) >= CANDIDATE_CUTOFF:
                        a, b = sorted((active[i], active[j]))
                        pairs.add((a, b))

        for position, column in enumerate(columns):
            if types[column] not in STRONG_KEY_TYPES:
                continue
            by_value: dict[str, list[int]] = defaultdict(list)
            for i in active:
                if rows[i][position]:
                    by_value[rows[i][position]].append(i)
            for members in by_value.values():
                for x in range(len(members)):
                    for y in range(x + 1, len(members)):
                        pairs.add((members[x], members[y]))
        return pairs

    @staticmethod
    def _pair_score(a: list[str], b: list[str], weights: list[float]) -> float:
        total = weight_sum = 0.0
        for x, y, weight in zip(a, b, weights, strict=True):
            if not x or not y:
                continue
            total += fuzz.ratio(x, y) * weight
            weight_sum += weight
        return total / weight_sum if weight_sum else 0.0

    @staticmethod
    def _choose_keeper(rows: list[list[str]], a: int, b: int) -> tuple[int, int]:
        """Keep the more complete row; on a tie keep the earlier one."""
        filled_a = sum(1 for x in rows[a] if x)
        filled_b = sum(1 for x in rows[b] if x)
        return (b, a) if filled_b > filled_a else (a, b)

    @staticmethod
    def _near_suggestion(context: DetectionContext, pair: DuplicatePair) -> Suggestion:
        listed = "; ".join(
            f'{column}: "{kept}" vs "{dropped}"'
            for column, kept, dropped in pair.differences[:MAX_LISTED_DIFFERENCES]
        )
        more = len(pair.differences) - MAX_LISTED_DIFFERENCES
        if more > 0:
            listed += f"; and {more} more"
        return Suggestion(
            kind=IssueKind.NEAR_DUPLICATE,
            action=Action.DROP_ROW,
            row_index=pair.drop,
            related_row_index=pair.keep,
            reason=f"Probably the same record as row {pair.keep + 1} "
            f"({pair.score:.0f}% similar). Differences: {listed}.",
            confidence=round(pair.score / 100 * 0.85, 2),
            source=Source.RULE,
            group_key="near_duplicate",
        )
