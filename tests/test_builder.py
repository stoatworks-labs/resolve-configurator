from pathlib import Path

from resolve_configurator.builder import build_plan, render_plan
from resolve_configurator.config import load_config
from resolve_configurator.csv_reader import read_csv
from resolve_configurator.model import build_show

REPO = Path(__file__).resolve().parents[1]


def _plan():
    config = load_config(REPO / "project.example.toml")
    rows = read_csv(REPO / "sample-sessions.csv")
    show = build_show(rows, config.default_session_minutes)
    return build_plan(show, config), config


def test_project_name_expands_earliest_date():
    plan, _ = _plan()
    assert plan.project_name == "MyEvent 2026-08-03"


def test_settings_include_format():
    plan, _ = _plan()
    assert plan.settings["timelineFrameRate"] == "25"
    assert plan.settings["timelineResolutionWidth"] == "1920"
    assert plan.settings["timelineResolutionHeight"] == "1080"


def test_top_level_bins_assets_first_then_theatres():
    plan, _ = _plan()
    names = [n.name for n in plan.root_children]
    assert names[0] == "Assets"
    assert names[1:] == ["Globe", "Rose", "Swan"]


def test_assets_bins_populated():
    plan, _ = _plan()
    assets = next(n for n in plan.root_children if n.name == "Assets")
    backgrounds = next(c for c in assets.children if c.name == "Backgrounds")
    assert {p.name for p in backgrounds.media} == {"pip-blue.png", "pip-warm.png"}


def test_theatre_scoped_asset_nested_under_theatre():
    plan, _ = _plan()
    globe = next(n for n in plan.root_children if n.name == "Globe")
    globe_assets = next(c for c in globe.children if c.name == "Assets")
    slides = next(c for c in globe_assets.children if c.name == "Slides")
    assert [p.name for p in slides.media] == ["globe-title.png"]


def test_day_bins_and_timelines():
    plan, _ = _plan()
    globe = next(n for n in plan.root_children if n.name == "Globe")
    day = next(c for c in globe.children if c.name == "2026-08-03")
    # colons are replaced by the shared name sanitiser (09:30 -> 09-30)
    assert day.timelines == ["09-30 - Alice Nguyen", "11-00 - Marcus Reid"]


def test_planned_session_count_matches_csv():
    plan, _ = _plan()
    assert len(plan.planned_sessions) == 6


def test_render_plan_is_readable():
    plan, _ = _plan()
    text = render_plan(plan)
    assert "MyEvent 2026-08-03" in text
    assert "▸ 09-30 - Alice Nguyen" in text
    assert "timelineFrameRate = 25" in text


def test_timeline_name_collision_disambiguated():
    # Two sessions that would render to the same name must not collide.
    from resolve_configurator.model import build_show as bs

    rows = [
        {"date": "2026-01-01", "theatre": "A", "start time": "09:00",
         "presenter name": "Same", "presenter email": "s@e.com", "_row_number": "2"},
        {"date": "2026-01-02", "theatre": "A", "start time": "09:00",
         "presenter name": "Same", "presenter email": "s@e.com", "_row_number": "3"},
    ]
    config = load_config(REPO / "project.example.toml")
    plan = build_plan(bs(rows, config.default_session_minutes), config)
    names = [ps.timeline_name for ps in plan.planned_sessions]
    assert len(set(names)) == 2
