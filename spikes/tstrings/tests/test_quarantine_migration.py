"""Migration of the retired legacy training data into quarantine."""

import pytest
from scripts.quarantine_legacy_examples import parse_legacy_line, slugify

LINE = (
    '{"text": "# Python 3.14 t-strings: access the static string parts\\n'
    'name = \\"World\\"\\ntemplate = t\\"Hello {name}!\\""}'
)


def test_parse_extracts_description() -> None:
    assert parse_legacy_line(LINE).description == "access the static string parts"


def test_parse_extracts_code_without_header() -> None:
    record = parse_legacy_line(LINE)

    assert record.code == 'name = "World"\ntemplate = t"Hello {name}!"'
    assert "# Python 3.14 t-strings" not in record.code


def test_parse_sets_id_from_description() -> None:
    assert parse_legacy_line(LINE).id == "access-the-static-string-parts"


def test_parse_marks_provenance_and_reason() -> None:
    record = parse_legacy_line(LINE)

    assert record.provenance == "unverified"
    assert "F-CONTAM" in record.reason


def test_parse_rejects_unexpected_header() -> None:
    bad = '{"text": "# Some other header\\nx = 1"}'

    with pytest.raises(ValueError, match="unexpected header"):
        parse_legacy_line(bad)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("use a !r conversion", "use-a-r-conversion"),
        ("read the  evaluated value", "read-the-evaluated-value"),
        ("Trailing punctuation!", "trailing-punctuation"),
    ],
)
def test_slugify(description: str, expected: str) -> None:
    assert slugify(description) == expected
