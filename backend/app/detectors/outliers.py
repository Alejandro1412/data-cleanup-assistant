"""Numeric and date values far outside the rest of the column.

Uses the modified z-score (median and MAD) rather than mean and standard
deviation: a single extreme value inflates the standard deviation enough to
hide itself, while the median and MAD barely move.

A value that looks extreme for the whole column can be normal for its group:
an Enterprise plan costs far more than a Basic one. So a numeric outlier is
only reported if it is also an outlier inside every small categorical group
it belongs to (when such groups exist and are large enough to judge).
"""

from __future__ import annotations

import statistics
from datetime import datetime

from app.detectors.base import DetectionContext
from app.domain.models import Action, ColumnType, IssueKind, Source, Suggestion
from app.pipeline import values as v

MODIFIED_Z_THRESHOLD = 3.5
MIN_VALUES = 8
MAX_GROUPS = 12
NON_NEGATIVE_SHARE = 0.98
EARLIEST_PLAUSIBLE_YEAR = 1900


def _fmt(number: float) -> str:
    return f"{number:,.0f}" if abs(number) >= 100 or number.is_integer() else f"{number:,.2f}"


def _modified_z(number: float, median: float, mad: float) -> float:
    return 0.6745 * (number - median) / mad


def _robust_center(numbers: list[float]) -> tuple[float, float]:
    median = statistics.median(numbers)
    return median, statistics.median(abs(n - median) for n in numbers)


def _percentile(sorted_values: list[float], q: float) -> float:
    index = max(0, min(len(sorted_values) - 1, round(q * (len(sorted_values) - 1))))
    return sorted_values[index]


class OutlierDetector:
    name = "outliers"
    stage = 40

    def detect(self, context: DetectionContext) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for column in context.columns_of(ColumnType.INTEGER, ColumnType.FLOAT):
            suggestions.extend(self._numeric(context, column))
        for column in context.columns_of(ColumnType.DATE):
            suggestions.extend(self._dates(context, column))
        return suggestions

    def _numeric(self, context: DetectionContext, column: str) -> list[Suggestion]:
        cells = [
            (row, value, number)
            for row, value in context.cells(column)
            if (number := v.parse_number(value)) is not None
        ]
        if len(cells) < MIN_VALUES:
            return []
        numbers = sorted(number for _, _, number in cells)
        median, mad = _robust_center(numbers)
        groups = self._group_stats(context, cells)
        typical = (
            f"half of all values fall between {_fmt(_percentile(numbers, 0.25))} "
            f"and {_fmt(_percentile(numbers, 0.75))}"
        )
        non_negative_share = sum(1 for n in numbers if n >= 0) / len(numbers)

        found = []
        for row, value, number in cells:
            if number < 0 and non_negative_share >= NON_NEGATIVE_SHARE:
                found.append(
                    self._flag(
                        row,
                        column,
                        value,
                        f"Negative value in a column where every other value is zero or "
                        f"positive; {typical}.",
                        0.85,
                        f"negative:{column}",
                    )
                )
                continue
            if mad == 0:
                continue
            modified_z = _modified_z(number, median, mad)
            if abs(modified_z) > MODIFIED_Z_THRESHOLD and self._extreme_in_groups(
                row, number, groups
            ):
                found.append(
                    self._flag(
                        row,
                        column,
                        value,
                        f"Unusually {'high' if modified_z > 0 else 'low'} for {column}: "
                        f"the median is {_fmt(median)} and {typical}.",
                        round(min(0.95, 0.55 + abs(modified_z) / 40), 2),
                        f"outlier:{column}",
                    )
                )
        return found

    @staticmethod
    def _group_stats(
        context: DetectionContext, cells: list[tuple[int, str, float]]
    ) -> list[tuple[list[str], dict[str, tuple[float, float]]]]:
        """For each low-cardinality categorical column: row labels and per-label
        (median, MAD), keeping only labels with enough values to judge."""
        result = []
        for column in context.columns_of(ColumnType.CATEGORICAL):
            if context.profiles[column].distinct_count > MAX_GROUPS:
                continue
            labels = [str(x).strip().lower() for x in context.frame[column].tolist()]
            by_label: dict[str, list[float]] = {}
            for row, _, number in cells:
                by_label.setdefault(labels[row], []).append(number)
            stats = {
                label: _robust_center(values)
                for label, values in by_label.items()
                if len(values) >= MIN_VALUES
            }
            if len(stats) > 1:
                result.append((labels, stats))
        return result

    @staticmethod
    def _extreme_in_groups(
        row: int, number: float, groups: list[tuple[list[str], dict[str, tuple[float, float]]]]
    ) -> bool:
        for labels, stats in groups:
            center = stats.get(labels[row])
            if center is None:
                continue
            median, mad = center
            if mad > 0 and abs(_modified_z(number, median, mad)) <= MODIFIED_Z_THRESHOLD:
                return False
        return True

    def _dates(self, context: DetectionContext, column: str) -> list[Suggestion]:
        cells = [(row, value) for row, value in context.cells(column) if not v.is_null(value)]
        order = v.pick_date_format([value for _, value in cells])
        latest_plausible = datetime.now().year + 1
        found = []
        for row, value in cells:
            fmt = v.resolve_date_format(value, order)
            if fmt is None:
                continue
            year = datetime.strptime(value.strip(), fmt).year
            if year < EARLIEST_PLAUSIBLE_YEAR or year > latest_plausible:
                found.append(
                    self._flag(
                        row,
                        column,
                        value,
                        f"The year {year} is outside the plausible range "
                        f"({EARLIEST_PLAUSIBLE_YEAR}-{latest_plausible}).",
                        0.85,
                        f"date_range:{column}",
                    )
                )
        return found

    @staticmethod
    def _flag(
        row: int, column: str, value: str, reason: str, confidence: float, group_key: str
    ) -> Suggestion:
        return Suggestion(
            kind=IssueKind.OUTLIER,
            action=Action.FLAG,
            row_index=row,
            column=column,
            current_value=value,
            reason=reason,
            confidence=confidence,
            source=Source.RULE,
            group_key=group_key,
        )
