from pathlib import Path

from resolve_configurator.builder import build_plan
from resolve_configurator.config import load_config
from resolve_configurator.csv_reader import read_csv
from resolve_configurator.model import build_show
from resolve_configurator.smartbins import build_recipes, render_markdown, write_recipes

REPO = Path(__file__).resolve().parents[1]


def _setup():
    config = load_config(REPO / "project.example.toml")
    rows = read_csv(REPO / "sample-sessions.csv")
    show = build_show(rows, config.default_session_minutes)
    plan = build_plan(show, config)
    return plan, config


def test_recipe_rules_for_a_session():
    plan, config = _setup()
    recipes = build_recipes(plan.planned_sessions, config.drives)
    globe_first = next(
        r for r in recipes if r.theatre == "Globe" and r.smart_bin_name == "09-30 - Alice Nguyen"
    )
    rules = {(c.field, c.operator): c.value for c in globe_first.criteria}
    assert rules[("File Path", "Contains")] == "REC_GLOBE_01"
    assert rules[("Date Created", "is")] == "2026-08-03"
    assert rules[("Start TC", "is in the range")] == ["09:30:00:00", "11:00:00:00"]
    assert globe_first.warnings == []


def test_missing_drive_produces_warning():
    plan, _ = _setup()
    recipes = build_recipes(plan.planned_sessions, drives={})  # no drives mapped
    assert all(
        any("No record drive mapped" in w for w in r.warnings) for r in recipes
    )
    # ...and no File Path rule when there's no drive
    assert all(
        all(c.field != "File Path" for c in r.criteria) for r in recipes
    )


def test_markdown_contains_rules():
    plan, config = _setup()
    recipes = build_recipes(plan.planned_sessions, config.drives)
    md = render_markdown(recipes)
    assert "## Globe" in md
    assert "REC_GLOBE_01" in md
    assert "09:30:00:00 .. 11:00:00:00" in md


def test_write_recipes_creates_files(tmp_path):
    plan, config = _setup()
    recipes = build_recipes(plan.planned_sessions, config.drives)
    md_path, json_path = write_recipes(recipes, tmp_path)
    assert md_path.exists() and json_path.exists()
    assert "smart-bins.md" == md_path.name
