"""Read the 5-column session CSV.

Semantics are ported from nc-filedropbatch's CsvReader.php so both tools accept
exactly the same files:
    Date, Theatre, Start Time, presenter name, presenter email
- headers are matched case-insensitively after trimming;
- a UTF-8 BOM on the first header is tolerated;
- every value is trimmed;
- fully-blank lines are skipped;
- a missing required column is a hard error.

parse_rows() also accepts already-parsed rows (e.g. from a spreadsheet export),
mirroring the PHP method of the same name.
"""

from __future__ import annotations

import csv
from pathlib import Path

# canonical (lowercase) header -> display name used in error messages
REQUIRED_HEADERS: dict[str, str] = {
    "date": "Date",
    "theatre": "Theatre",
    "start time": "Start Time",
    "presenter name": "presenter name",
    "presenter email": "presenter email",
}


class CsvError(ValueError):
    """Raised when the CSV is empty or missing required columns."""


def read_csv(path: str | Path) -> list[dict[str, str]]:
    """Read the CSV at *path* and return a list of canonical row dicts."""
    # utf-8-sig transparently strips a leading BOM if present.
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    return parse_rows(rows)


def parse_rows(lines: list[list[str]]) -> list[dict[str, str]]:
    """Validate + shape rows already parsed into lists (first line = header)."""
    if not lines:
        raise CsvError("The CSV is empty")

    column_map = _map_columns(lines[0])

    out: list[dict[str, str]] = []
    for index, line in enumerate(lines[1:], start=2):  # row 1 is the header
        if _is_blank(line):
            continue
        row: dict[str, str] = {"_row_number": str(index)}
        for canonical, col in column_map.items():
            value = line[col] if col < len(line) else ""
            row[canonical] = value.strip()
        out.append(row)
    return out


def _is_blank(line: list[str]) -> bool:
    return all(cell.strip() == "" for cell in line)


def _map_columns(header_row: list[str]) -> dict[str, int]:
    # Tolerate a UTF-8 BOM on the first header even when rows were parsed
    # elsewhere (read_csv already strips it via utf-8-sig, but parse_rows may not).
    normalized = {
        str(name).replace("﻿", "").strip().lower(): i for i, name in enumerate(header_row)
    }

    column_map: dict[str, int] = {}
    missing: list[str] = []
    for canonical, display in REQUIRED_HEADERS.items():
        if canonical in normalized:
            column_map[canonical] = normalized[canonical]
        else:
            missing.append(display)

    if missing:
        raise CsvError("The CSV is missing required column(s): " + ", ".join(missing))
    return column_map
