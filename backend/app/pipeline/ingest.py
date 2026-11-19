"""CSV loading.

Every cell is read as a string and empty cells stay as empty strings. Letting
pandas coerce types or turn "NA" into NaN would destroy the exact values we
need to report on and later write back.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import pandas as pd
from charset_normalizer import from_bytes

CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]
SNIFF_BYTES = 64 * 1024


class IngestError(ValueError):
    pass


@dataclass(frozen=True)
class IngestResult:
    frame: pd.DataFrame
    encoding: str
    delimiter: str


def detect_encoding(raw: bytes) -> str:
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        best = from_bytes(raw[: SNIFF_BYTES * 4]).best()
        if best is None:
            raise IngestError("Could not detect the file encoding.") from None
        return best.encoding
    return "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"


def detect_delimiter(text: str) -> str:
    sample = text[:SNIFF_BYTES]
    try:
        return csv.Sniffer().sniff(sample, delimiters="".join(CANDIDATE_DELIMITERS)).delimiter
    except csv.Error:
        # Sniffer gives up on single-column files and some quoted layouts.
        first_line = sample.splitlines()[0] if sample else ""
        counts = {d: first_line.count(d) for d in CANDIDATE_DELIMITERS}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] > 0 else ","


def _clean_headers(columns: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: dict[str, int] = {}
    for position, name in enumerate(columns, start=1):
        base = str(name).strip() or f"column_{position}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        cleaned.append(base if count == 0 else f"{base}_{count + 1}")
    return cleaned


def load_csv(
    raw: bytes, max_rows: int, encoding: str | None = None, delimiter: str | None = None
) -> IngestResult:
    if not raw.strip():
        raise IngestError("The file is empty.")

    encoding = encoding or detect_encoding(raw)
    text = raw.decode(encoding, errors="replace")
    delimiter = delimiter or detect_delimiter(text)

    try:
        frame = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            skip_blank_lines=True,
        )
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise IngestError(f"Could not parse the file as CSV: {exc}") from exc

    if frame.empty or len(frame.columns) == 0:
        raise IngestError("The file has a header but no data rows.")
    if len(frame) > max_rows:
        raise IngestError(f"The file has {len(frame):,} rows; the limit is {max_rows:,}.")

    frame.columns = pd.Index(_clean_headers([str(c) for c in frame.columns]))
    frame = frame.reset_index(drop=True).astype(object)
    return IngestResult(frame=frame, encoding=encoding, delimiter=delimiter)
