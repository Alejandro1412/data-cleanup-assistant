"""Formatting problems: stray whitespace, mixed date/phone/number/boolean styles
and values that do not fit the column type at all."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from app.detectors.base import DetectionContext
from app.domain.models import Action, ColumnType, IssueKind, Source, Suggestion
from app.pipeline import values as v

FORMAT_LABELS = {
    "%Y-%m-%d": "YYYY-MM-DD",
    "%Y/%m/%d": "YYYY/MM/DD",
    "%m/%d/%Y": "MM/DD/YYYY",
    "%d/%m/%Y": "DD/MM/YYYY",
    "%m-%d-%Y": "MM-DD-YYYY",
    "%d-%m-%Y": "DD-MM-YYYY",
    "%d.%m.%Y": "DD.MM.YYYY",
}
MAX_INVALID_PHONE_SHARE = 0.5
BOOLEAN_PAIRS = {
    "true": "false",
    "True": "False",
    "TRUE": "FALSE",
    "yes": "no",
    "Yes": "No",
    "YES": "NO",
    "y": "n",
    "Y": "N",
    "t": "f",
    "T": "F",
    "1": "0",
}


def _phone_shape(value: str) -> str:
    return re.sub(r"\d", "9", value.strip())


class FormatDetector:
    name = "formats"
    stage = 20

    def detect(self, context: DetectionContext) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for column, profile in context.profiles.items():
            kind = profile.inferred_type
            if kind is ColumnType.EMPTY:
                continue
            suggestions.extend(
                self._whitespace(
                    context,
                    column,
                    skip_typed=kind
                    in {
                        ColumnType.EMAIL,
                        ColumnType.DATE,
                        ColumnType.PHONE,
                        ColumnType.BOOLEAN,
                        ColumnType.INTEGER,
                        ColumnType.FLOAT,
                    },
                )
            )
            if kind is ColumnType.EMAIL:
                suggestions.extend(self._emails(context, column))
            elif kind is ColumnType.PHONE:
                suggestions.extend(self._phones(context, column))
            elif kind is ColumnType.DATE:
                suggestions.extend(self._dates(context, column))
            elif kind in (ColumnType.INTEGER, ColumnType.FLOAT):
                suggestions.extend(self._numbers(context, column))
            elif kind is ColumnType.BOOLEAN:
                suggestions.extend(self._booleans(context, column))
        return suggestions

    @staticmethod
    def _non_null(context: DetectionContext, column: str) -> list[tuple[int, str]]:
        return [(row, value) for row, value in context.cells(column) if not v.is_null(value)]

    def _whitespace(
        self, context: DetectionContext, column: str, skip_typed: bool
    ) -> list[Suggestion]:
        # Typed columns get whitespace fixed as part of their own normalization,
        # which keeps it to one suggestion per cell.
        if skip_typed:
            return []
        found = []
        for row, value in self._non_null(context, column):
            cleaned = v.collapse_whitespace(value)
            if cleaned != value:
                found.append(
                    _set_value(
                        IssueKind.INCONSISTENT_FORMAT,
                        row,
                        column,
                        value,
                        cleaned,
                        "Extra spaces before, after or inside the value.",
                        0.99,
                        f"whitespace:{column}",
                    )
                )
        return found

    def _emails(self, context: DetectionContext, column: str) -> list[Suggestion]:
        found = []
        for row, value in self._non_null(context, column):
            trimmed = value.strip()
            if v.is_email(trimmed):
                normalized = trimmed.lower()
                if normalized != value:
                    found.append(
                        _set_value(
                            IssueKind.INCONSISTENT_FORMAT,
                            row,
                            column,
                            value,
                            normalized,
                            "Email addresses are case-insensitive; storing them in lowercase "
                            "makes matching and deduplication reliable.",
                            0.95,
                            f"email_case:{column}",
                        )
                    )
                continue

            repaired = trimmed.replace(" ", "").replace(",", ".").lower()
            repaired = re.sub(r"@+", "@", repaired)
            if v.is_email(repaired):
                found.append(
                    _set_value(
                        IssueKind.INVALID_VALUE,
                        row,
                        column,
                        value,
                        repaired,
                        "Not a valid email as written. The proposed value removes spaces, "
                        "doubled @ signs or a comma typed instead of a dot.",
                        0.7,
                        f"email_repair:{column}",
                    )
                )
            else:
                found.append(
                    _flag(
                        IssueKind.INVALID_VALUE,
                        row,
                        column,
                        value,
                        "Not a valid email address.",
                        0.9,
                        f"email_invalid:{column}",
                    )
                )
        return found

    def _phones(self, context: DetectionContext, column: str) -> list[Suggestion]:
        cells = self._non_null(context, column)
        shapes = Counter(_phone_shape(value) for _, value in cells)
        mixed = len(shapes) > 1
        normalized_cells = [
            (row, value, v.normalize_phone(value, context.phone_region)) for row, value in cells
        ]
        invalid_share = sum(1 for *_, n in normalized_cells if n is None) / max(1, len(cells))
        if invalid_share > MAX_INVALID_PHONE_SHARE:
            # Most numbers failing validation means the configured region is
            # probably wrong for this file; flagging them all would be noise.
            return []
        found = []
        for row, value, normalized in normalized_cells:
            if normalized is None:
                found.append(
                    _flag(
                        IssueKind.INVALID_VALUE,
                        row,
                        column,
                        value,
                        "Not a valid phone number for the expected region.",
                        0.8,
                        f"phone_invalid:{column}",
                    )
                )
            elif mixed and normalized != value:
                found.append(
                    _set_value(
                        IssueKind.INCONSISTENT_FORMAT,
                        row,
                        column,
                        value,
                        normalized,
                        f"This column mixes {len(shapes)} phone formats. E.164 "
                        "(+15551234567) is unambiguous and works with any phone system.",
                        0.9,
                        f"phone_format:{column}",
                    )
                )
        return found

    def _dates(self, context: DetectionContext, column: str) -> list[Suggestion]:
        cells = self._non_null(context, column)
        order = v.pick_date_format([value for _, value in cells])
        parsed: list[tuple[int, str, str | None]] = [
            (row, value, v.resolve_date_format(value, order)) for row, value in cells
        ]
        formats_used = {fmt for _, _, fmt in parsed if fmt}
        found = []
        for row, value, fmt in parsed:
            if fmt is None:
                found.append(
                    _flag(
                        IssueKind.INVALID_VALUE,
                        row,
                        column,
                        value,
                        "Expected a date, but this value could not be read as one.",
                        0.85,
                        f"date_invalid:{column}",
                    )
                )
                continue
            if len(formats_used) == 1:
                if value != value.strip():
                    found.append(
                        _set_value(
                            IssueKind.INCONSISTENT_FORMAT,
                            row,
                            column,
                            value,
                            value.strip(),
                            "Extra spaces before or after the value.",
                            0.99,
                            f"whitespace:{column}",
                        )
                    )
                continue
            iso = datetime.strptime(value.strip(), fmt).strftime(v.ISO_DATE)
            if iso == value:
                continue
            label = FORMAT_LABELS.get(fmt, "text")
            reason = f"This column mixes {len(formats_used)} date formats. Converting {label} to "
            reason += "ISO 8601 (YYYY-MM-DD) so every date is read the same way."
            confidence = 0.95
            if order is None and v.is_ambiguous_date(value):
                reason += " The day and month could be swapped here; please check."
                confidence = 0.6
            found.append(
                _set_value(
                    IssueKind.INCONSISTENT_FORMAT,
                    row,
                    column,
                    value,
                    iso,
                    reason,
                    confidence,
                    f"date_format:{column}:{label}",
                )
            )
        return found

    def _numbers(self, context: DetectionContext, column: str) -> list[Suggestion]:
        found = []
        for row, value in self._non_null(context, column):
            if v.is_plain_number(value) and value == value.strip():
                continue
            number = v.parse_number(value)
            if number is None:
                found.append(
                    _flag(
                        IssueKind.INVALID_VALUE,
                        row,
                        column,
                        value,
                        "Expected a number in this column.",
                        0.9,
                        f"number_invalid:{column}",
                    )
                )
                continue
            found.append(
                _set_value(
                    IssueKind.INCONSISTENT_FORMAT,
                    row,
                    column,
                    value,
                    v.format_number(number),
                    "Number stored with currency symbols, thousands separators, a percent "
                    "sign or spaces. Plain numbers can be sorted and summed.",
                    0.85,
                    f"number_format:{column}",
                )
            )
        return found

    def _booleans(self, context: DetectionContext, column: str) -> list[Suggestion]:
        cells = self._non_null(context, column)
        styles = Counter(value.strip() for _, value in cells)
        if len(styles) <= 2:
            return []
        true_style = next(
            (
                s
                for s, _ in styles.most_common()
                if s.lower() in v.TRUE_TOKENS and s in BOOLEAN_PAIRS
            ),
            "true",
        )
        false_style = BOOLEAN_PAIRS[true_style]
        found = []
        for row, value in cells:
            target = true_style if v.boolean_value(value) else false_style
            if value != target:
                found.append(
                    _set_value(
                        IssueKind.INCONSISTENT_FORMAT,
                        row,
                        column,
                        value,
                        target,
                        f"Yes/no values are written {len(styles)} different ways. Using "
                        f'"{true_style}"/"{false_style}", the most common style.',
                        0.9,
                        f"boolean_format:{column}",
                    )
                )
        return found


def _set_value(
    kind: IssueKind,
    row: int,
    column: str,
    current: str,
    proposed: str,
    reason: str,
    confidence: float,
    group_key: str,
) -> Suggestion:
    return Suggestion(
        kind=kind,
        action=Action.SET_VALUE,
        row_index=row,
        column=column,
        current_value=current,
        proposed_value=proposed,
        reason=reason,
        confidence=confidence,
        source=Source.RULE,
        group_key=group_key,
    )


def _flag(
    kind: IssueKind,
    row: int,
    column: str,
    current: str,
    reason: str,
    confidence: float,
    group_key: str,
) -> Suggestion:
    return Suggestion(
        kind=kind,
        action=Action.FLAG,
        row_index=row,
        column=column,
        current_value=current,
        reason=reason,
        confidence=confidence,
        source=Source.RULE,
        group_key=group_key,
    )
