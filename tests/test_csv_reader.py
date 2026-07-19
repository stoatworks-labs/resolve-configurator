from pathlib import Path

import pytest

from resolve_configurator.csv_reader import CsvError, parse_rows, read_csv

REPO = Path(__file__).resolve().parents[1]


def test_reads_sample():
    rows = read_csv(REPO / "sample-sessions.csv")
    assert len(rows) == 6
    assert rows[0]["theatre"] == "Globe"
    assert rows[0]["start time"] == "09:30"
    assert rows[0]["presenter email"] == "alice.nguyen@example.com"
    assert rows[0]["_row_number"] == "2"


def test_reads_edge_cases_all_rows_kept():
    # The reader itself keeps every non-blank row; dedup happens in the model.
    rows = read_csv(REPO / "sample-sessions-edge-cases.csv")
    assert len(rows) == 7


def test_case_insensitive_headers_and_bom():
    lines = [
        ["﻿DATE", "theatre", "START TIME", "Presenter Name", "presenter email"],
        ["2026-01-01", "A", "09:00", "X", "x@e.com"],
    ]
    rows = parse_rows(lines)
    assert rows[0]["date"] == "2026-01-01"
    assert rows[0]["theatre"] == "A"


def test_values_are_trimmed():
    lines = [
        ["Date", "Theatre", "Start Time", "presenter name", "presenter email"],
        ["  2026-01-01 ", " A ", " 09:00 ", "  X  ", " x@e.com "],
    ]
    rows = parse_rows(lines)
    assert rows[0]["theatre"] == "A"
    assert rows[0]["presenter name"] == "X"


def test_blank_rows_skipped():
    lines = [
        ["Date", "Theatre", "Start Time", "presenter name", "presenter email"],
        ["", "", "", "", ""],
        ["2026-01-01", "A", "09:00", "X", "x@e.com"],
        [],
    ]
    rows = parse_rows(lines)
    assert len(rows) == 1


def test_missing_column_raises():
    with pytest.raises(CsvError) as exc:
        parse_rows([["Date", "Theatre", "Start Time", "presenter name"]])
    assert "presenter email" in str(exc.value)


def test_empty_raises():
    with pytest.raises(CsvError):
        parse_rows([])
