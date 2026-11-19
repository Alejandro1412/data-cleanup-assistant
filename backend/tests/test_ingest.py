import pytest

from app.pipeline.ingest import IngestError, load_csv


def test_reads_every_cell_as_an_unchanged_string() -> None:
    result = load_csv(b"zip,flag,note\n00123,NA,\n", max_rows=10)

    assert result.frame.iloc[0].tolist() == ["00123", "NA", ""]


def test_detects_semicolon_delimiter() -> None:
    result = load_csv(b"a;b\n1;2\n3;4\n", max_rows=10)

    assert result.delimiter == ";"
    assert list(result.frame.columns) == ["a", "b"]


def test_handles_utf8_bom() -> None:
    result = load_csv("name\nJosé\n".encode("utf-8-sig"), max_rows=10)

    assert result.encoding == "utf-8-sig"
    assert list(result.frame.columns) == ["name"]


def test_falls_back_to_detected_encoding_for_latin1() -> None:
    raw = "name,city\nJosé,Bogotá\nAndrés,Medellín\n".encode("latin-1")

    result = load_csv(raw, max_rows=10)

    assert result.frame.at[0, "city"] == "Bogotá"


def test_renames_blank_and_repeated_headers() -> None:
    result = load_csv(b"name, ,name\na,b,c\n", max_rows=10)

    assert list(result.frame.columns) == ["name", "column_2", "name.1"]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"", "empty"),
        (b"a,b\n", "no data rows"),
        (b"a,b\n1,2\n3,4\n5,6\n", "limit is 2"),
    ],
)
def test_rejects_unusable_files(raw: bytes, message: str) -> None:
    with pytest.raises(IngestError, match=message):
        load_csv(raw, max_rows=2)
