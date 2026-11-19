"""Column profiling and type inference.

The inferred type drives which detectors run on a column, so the rules here are
deliberately conservative: a column is only treated as numeric, date, etc. when
a clear majority of its non-empty values agree.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Callable

import pandas as pd

from app.domain.models import ColumnProfile, ColumnType
from app.pipeline import values as v

TYPE_THRESHOLD = 0.8
IDENTIFIER_NAME_RE = re.compile(r"(^id$|_id$|^id_|uuid|guid|^key$|_key$)", re.IGNORECASE)
PHONE_NAME_RE = re.compile(r"phone|mobile|cell|tel|fax", re.IGNORECASE)
EMAIL_NAME_RE = re.compile(r"e-?mail", re.IGNORECASE)
# A column named like "phone" or "email" only needs a bare majority of matching
# values, so that a column with many broken entries is still checked as one.
NAMED_TYPE_THRESHOLD = 0.5
MAX_CATEGORICAL_DISTINCT = 100
MAX_CATEGORICAL_RATIO = 0.5
SAMPLE_SIZE = 8
TOP_VALUES = 15


def _share(items: list[str], predicate: Callable[[str], bool]) -> float:
    if not items:
        return 0.0
    return sum(1 for item in items if predicate(item)) / len(items)


def infer_type(name: str, non_null: list[str]) -> tuple[ColumnType, float]:
    if not non_null:
        return ColumnType.EMPTY, 1.0

    distinct = {item.strip() for item in non_null}
    uniqueness = len(distinct) / len(non_null)

    # Plain 0/1 columns are left as integers; they are often counts or codes.
    if all(v.is_boolean(item) for item in distinct) and not all(
        item.isdigit() for item in distinct
    ):
        return ColumnType.BOOLEAN, 1.0

    if IDENTIFIER_NAME_RE.search(name) and uniqueness >= 0.95:
        return ColumnType.IDENTIFIER, uniqueness

    email_share = _share(non_null, v.looks_like_email)
    named_email = bool(EMAIL_NAME_RE.search(name))
    if email_share >= (NAMED_TYPE_THRESHOLD if named_email else TYPE_THRESHOLD):
        return ColumnType.EMAIL, email_share

    phone_share = _share(non_null, v.looks_like_phone)
    if PHONE_NAME_RE.search(name) and phone_share >= NAMED_TYPE_THRESHOLD:
        return ColumnType.PHONE, phone_share

    date_share = _share(non_null, lambda item: bool(v.matching_date_formats(item)))
    if date_share >= TYPE_THRESHOLD:
        return ColumnType.DATE, date_share

    numbers = [v.parse_number(item) for item in non_null]
    parsed = [n for n in numbers if n is not None]
    number_share = len(parsed) / len(non_null)
    if number_share >= TYPE_THRESHOLD:
        if all(v.is_integer_like(n) for n in parsed):
            return ColumnType.INTEGER, number_share
        return ColumnType.FLOAT, number_share

    if len(distinct) <= MAX_CATEGORICAL_DISTINCT and uniqueness <= MAX_CATEGORICAL_RATIO:
        return ColumnType.CATEGORICAL, 1.0

    return ColumnType.TEXT, 1.0


def profile_column(name: str, series: pd.Series) -> ColumnProfile:
    raw = [str(item) for item in series.tolist()]
    non_null = [item for item in raw if not v.is_null(item)]
    inferred, confidence = infer_type(name, non_null)

    counts = Counter(item.strip() for item in non_null)
    numeric_summary = None
    if inferred in (ColumnType.INTEGER, ColumnType.FLOAT):
        numbers = [n for n in (v.parse_number(item) for item in non_null) if n is not None]
        if numbers:
            numeric_summary = {
                "min": min(numbers),
                "max": max(numbers),
                "mean": round(statistics.fmean(numbers), 4),
                "median": statistics.median(numbers),
            }

    # First distinct values in file order are more useful than random ones.
    samples = list(dict.fromkeys(item.strip() for item in non_null))[:SAMPLE_SIZE]

    return ColumnProfile(
        name=name,
        inferred_type=inferred,
        non_null_count=len(non_null),
        null_count=len(raw) - len(non_null),
        distinct_count=len(counts),
        type_confidence=confidence,
        sample_values=samples,
        top_values=counts.most_common(TOP_VALUES),
        numeric_summary=numeric_summary,
    )


def profile_frame(frame: pd.DataFrame) -> dict[str, ColumnProfile]:
    return {str(column): profile_column(str(column), frame[column]) for column in frame.columns}
