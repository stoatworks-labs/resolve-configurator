from pathlib import Path

from resolve_configurator.cli import run

REPO = Path(__file__).resolve().parents[1]


def _capture():
    lines: list[str] = []
    return lines, lambda *a: lines.append(" ".join(str(x) for x in a))


def test_dry_run_sample(tmp_path):
    lines, log = _capture()
    rc = run(
        str(REPO / "sample-sessions.csv"),
        str(REPO / "project.example.toml"),
        dry_run=True,
        recipe_out=str(tmp_path),
        log=log,
    )
    out = "\n".join(lines)
    assert rc == 0
    assert (tmp_path / "smart-bins.md").exists()
    assert (tmp_path / "smart-bins.json").exists()
    assert "MyEvent 2026-08-03" in out
    assert "6 session(s) across 3 theatre(s)" in out


def test_dry_run_edge_cases(tmp_path):
    lines, log = _capture()
    rc = run(
        str(REPO / "sample-sessions-edge-cases.csv"),
        str(REPO / "project.example.toml"),
        dry_run=True,
        recipe_out=str(tmp_path),
        log=log,
    )
    out = "\n".join(lines)
    assert rc == 0
    # duplicate row dropped, one unparseable time reported
    assert "duplicate row(s) dropped" in out
    assert "unparseable start time" in out
    # empty theatre sanitises to a bin, slash theatre is escaped
    assert "untitled" in out
    assert "Globe - Studio" in out
