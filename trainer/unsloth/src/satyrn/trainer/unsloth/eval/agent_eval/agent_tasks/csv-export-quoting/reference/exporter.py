"""Export report rows for the finance team's spreadsheets and the warehouse system."""

import csv
import io

FIELDS = ["invoice", "customer", "amount", "note"]


def _cell(value) -> str:
    return "" if value is None else str(value)


def to_csv(rows: list[dict]) -> str:
    """CSV text: a header line, then one line per row, every line ending in a newline."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(FIELDS)
    for row in rows:
        writer.writerow(_cell(row.get(field)) for field in FIELDS)
    return out.getvalue()


def to_tsv(rows: list[dict]) -> str:
    """Tab-separated text for the warehouse system, which takes every field exactly as written."""
    lines = ["\t".join(FIELDS)]
    for row in rows:
        lines.append("\t".join(_cell(row.get(field)) for field in FIELDS))
    return "\n".join(lines) + "\n"
