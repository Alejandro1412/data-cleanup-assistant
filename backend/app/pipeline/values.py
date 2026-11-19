"""Parsing helpers shared by the profiler and the detectors."""

from __future__ import annotations

import re
from datetime import datetime

import phonenumbers

NULL_TOKENS = frozenset(
    {
        "",
        "na",
        "n/a",
        "n.a.",
        "nan",
        "null",
        "none",
        "nil",
        "-",
        "--",
        "?",
        "missing",
        "unknown",
        "undefined",
        "#n/a",
    }
)
TRUE_TOKENS = frozenset({"true", "t", "yes", "y", "1"})
FALSE_TOKENS = frozenset({"false", "f", "no", "n", "0"})

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_THOUSANDS_RE = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_CURRENCY_CHARS = "$€£¥"

# Order matters only for display; ambiguity between day-first and month-first
# formats is resolved per column in `pick_date_format`.
DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
    "%B %d %Y",
]
ISO_DATE = "%Y-%m-%d"
MONTH_FIRST = {"%m/%d/%Y", "%m-%d-%Y"}
DAY_FIRST = {"%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"}


def is_null(value: str | None) -> bool:
    return value is None or value.strip().lower() in NULL_TOKENS


def is_null_token(value: str) -> bool:
    """A placeholder such as "N/A" written instead of leaving the cell empty."""
    return value != "" and is_null(value)


def parse_number(value: str) -> float | None:
    """Parse plain numbers plus common human formats: 1,200  $45.00  12%."""
    text = value.strip()
    if not text:
        return None
    if _NUMBER_RE.match(text):
        return float(text)
    cleaned = text
    for symbol in _CURRENCY_CHARS:
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.removesuffix("%").strip()
    if _THOUSANDS_RE.match(cleaned):
        cleaned = cleaned.replace(",", "")
    if cleaned != text and _NUMBER_RE.match(cleaned):
        return float(cleaned)
    return None


def is_plain_number(value: str) -> bool:
    return bool(_NUMBER_RE.match(value.strip()))


def is_integer_like(number: float) -> bool:
    return number.is_integer()


def format_number(number: float) -> str:
    return str(int(number)) if number.is_integer() else repr(number)


def matching_date_formats(value: str) -> list[str]:
    text = value.strip()
    if not text or len(text) > 30:
        return []
    matches = []
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(text, fmt)
        except ValueError:
            continue
        matches.append(fmt)
    return matches


def pick_date_format(values: list[str]) -> str | None:
    """Decide between month-first and day-first using unambiguous values.

    "03/04/2024" fits both; "25/04/2024" only fits day-first. Majority of the
    unambiguous values wins. Returns None when the column gives no signal.
    """
    month_first = day_first = 0
    for value in values:
        formats = set(matching_date_formats(value))
        if formats & MONTH_FIRST and not formats & DAY_FIRST:
            month_first += 1
        elif formats & DAY_FIRST and not formats & MONTH_FIRST:
            day_first += 1
    if month_first == day_first:
        return None
    return "month_first" if month_first > day_first else "day_first"


def resolve_date_format(value: str, order: str | None) -> str | None:
    """The format to read `value` with, given the column's day/month order."""
    formats = matching_date_formats(value)
    if not formats:
        return None
    preferred = DAY_FIRST if order == "day_first" else MONTH_FIRST
    return next((f for f in formats if f in preferred), formats[0])


def is_ambiguous_date(value: str) -> bool:
    formats = set(matching_date_formats(value))
    return bool(formats & MONTH_FIRST and formats & DAY_FIRST)


def is_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value.strip()))


def looks_like_email(value: str) -> bool:
    return "@" in value


def normalize_phone(value: str, region: str) -> str | None:
    """Return E.164 if the number is valid, otherwise None."""
    text = value.strip()
    digits = sum(ch.isdigit() for ch in text)
    if digits < 7 or digits > 15:
        return None
    try:
        parsed = phonenumbers.parse(text, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def looks_like_phone(value: str) -> bool:
    text = value.strip()
    digits = sum(ch.isdigit() for ch in text)
    allowed = set("0123456789+-(). x")
    return 7 <= digits <= 15 and all(ch in allowed for ch in text.lower())


def boolean_value(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in TRUE_TOKENS:
        return True
    if lowered in FALSE_TOKENS:
        return False
    return None


def is_boolean(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered in TRUE_TOKENS or lowered in FALSE_TOKENS


def collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def normalize_key(value: str) -> str:
    """Comparison key: lowercase, no punctuation, single spaces."""
    lowered = re.sub(r"[.']", "", value.lower())
    without_punct = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(without_punct.split())
