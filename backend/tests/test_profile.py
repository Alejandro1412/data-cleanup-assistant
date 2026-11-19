import pandas as pd
import pytest

from app.domain.models import ColumnType
from app.pipeline.profile import infer_type, profile_column


@pytest.mark.parametrize(
    ("name", "values", "expected"),
    [
        ("customer_id", ["1", "2", "3", "4"], ColumnType.IDENTIFIER),
        ("email", ["a@x.com", "b@y.org", "c@z.io", "bad"], ColumnType.EMAIL),
        ("phone", ["(415) 555-0100", "415-555-0101", "4155550102"], ColumnType.PHONE),
        ("joined", ["2024-01-01", "01/02/2024", "2024-03-05"], ColumnType.DATE),
        ("qty", ["1", "2", "3", "40"], ColumnType.INTEGER),
        ("price", ["1.50", "$2.00", "3"], ColumnType.FLOAT),
        ("active", ["yes", "no", "Y", "true"], ColumnType.BOOLEAN),
        ("flag", ["0", "1", "1", "0"], ColumnType.INTEGER),
        ("country", ["US", "US", "MX", "US", "MX", "CA"], ColumnType.CATEGORICAL),
        ("notes", ["first note", "second", "third one", "fourth"], ColumnType.TEXT),
        ("empty", [], ColumnType.EMPTY),
    ],
)
def test_infers_column_type(name: str, values: list[str], expected: ColumnType) -> None:
    inferred, _ = infer_type(name, values)

    assert inferred is expected


def test_profile_counts_placeholders_as_missing() -> None:
    profile = profile_column("city", pd.Series(["Bogotá", "", "N/A", "Cali"], dtype=object))

    assert profile.null_count == 2
    assert profile.non_null_count == 2
    assert profile.null_ratio == 0.5


def test_profile_includes_numeric_summary() -> None:
    profile = profile_column("qty", pd.Series(["1", "2", "3", "10"], dtype=object))

    assert profile.numeric_summary == {"min": 1.0, "max": 10.0, "mean": 4.0, "median": 2.5}
