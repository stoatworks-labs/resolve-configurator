from pathlib import Path

from resolve_configurator.config import load_config
from resolve_configurator.core import execute
from resolve_configurator.csv_reader import read_csv

REPO = Path(__file__).resolve().parents[1]


def test_execute_dry_run_returns_result(tmp_path):
    rows = read_csv(REPO / "sample-sessions.csv")
    config = load_config(REPO / "project.example.toml")
    lines: list[str] = []
    result = execute(
        rows, config, dry_run=True, recipe_out=str(tmp_path), log=lambda *a: lines.append(str(a))
    )
    assert result.applied is False
    assert result.md_path.exists() and result.json_path.exists()
    assert len(result.plan.planned_sessions) == 6
    assert len(result.show.theatres) == 3


def test_execute_honours_config_overrides(tmp_path):
    # The GUI mutates the loaded Config before calling execute(); prove that path works.
    rows = read_csv(REPO / "sample-sessions.csv")
    config = load_config(REPO / "project.example.toml")
    config.project_name = "Overridden"
    config.frame_rate = "24"
    result = execute(rows, config, dry_run=True, recipe_out=str(tmp_path), log=lambda *a: None)
    assert result.plan.project_name == "Overridden"
    assert result.plan.settings["timelineFrameRate"] == "24"
