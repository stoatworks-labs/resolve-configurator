import io
import tomllib

from resolve_configurator import formmodel
from resolve_configurator.core import execute


def _session(date, theatre, start, name="P", email="p@e.com"):
    return {"date": date, "theatre": theatre, "start time": start,
            "presenter name": name, "presenter email": email}


def test_rows_from_sessions_shape_and_blank_drop():
    sessions = [
        _session("2026-08-03", "Globe", "09:30", "Alice", "a@e.com"),
        {"date": "", "theatre": "", "start time": "", "presenter name": "", "presenter email": ""},
        _session("2026-08-03", "Globe", "11:00", "Marcus", "m@e.com"),
    ]
    rows = formmodel.rows_from_sessions(sessions)
    assert len(rows) == 2
    assert rows[0]["_row_number"] == "2"  # header would be row 1
    assert rows[1]["_row_number"] == "4"  # blank row 3 skipped but still counted
    assert rows[0]["theatre"] == "Globe"
    assert set(rows[0]) == {"_row_number", *formmodel.SESSION_KEYS}


def test_distinct_theatres_first_seen_order():
    rows = formmodel.rows_from_sessions([
        _session("2026-08-05", "Swan", "13:00"),
        _session("2026-08-03", "Globe", "09:30"),
        _session("2026-08-03", "Globe", "11:00"),
    ])
    assert formmodel.distinct_theatres(rows) == ["Swan", "Globe"]


def test_build_config_assets_and_drives(tmp_path):
    img = tmp_path / "bg.png"
    img.write_bytes(b"x")
    config = formmodel.build_config(
        project_name="Show {date}", frame_rate="24", width=3840, height=2160,
        default_session_minutes=45,
        drives={"Globe": "REC_GLOBE_01", "": "ignored", "Empty": ""},
        assets=[
            {"path": str(img), "bin": "Backgrounds", "theatre": "Globe"},
            {"path": str(tmp_path / "missing.png"), "bin": "Slides", "theatre": None},
        ],
    )
    assert config.format_settings()["timelineResolutionWidth"] == "3840"
    assert config.format_settings()["timelineFrameRate"] == "24"
    assert config.drives == {"Globe": "REC_GLOBE_01"}  # blank keys/values dropped
    globe = next(a for a in config.assets if a.theatre == "Globe")
    assert globe.bin == "Backgrounds" and globe.missing is False
    slide = next(a for a in config.assets if a.theatre is None)
    assert slide.missing is True


def test_config_to_toml_roundtrips():
    config = formmodel.build_config(
        project_name="Show {date}", frame_rate="25", width=1920, height=1080,
        default_session_minutes=90,
        drives={"Globe": "REC_GLOBE_01"},
        assets=[{"path": "/tmp/a.png", "bin": "PiP", "theatre": "Globe"},
                {"path": "/tmp/b.png", "bin": "Slides", "theatre": None}],
    )
    data = tomllib.loads(formmodel.config_to_toml(config))
    assert data["project"]["name"] == "Show {date}"
    assert data["project"]["format"]["width"] == 1920
    assert data["drives"]["Globe"] == "REC_GLOBE_01"
    assert {a["bin"] for a in data["assets"]} == {"PiP", "Slides"}
    globe_asset = next(a for a in data["assets"] if a.get("theatre") == "Globe")
    assert globe_asset["bin"] == "PiP"


def test_end_to_end_dry_run(tmp_path):
    rows = formmodel.rows_from_sessions([
        _session("2026-08-03", "Globe", "09:30", "Alice"),
        _session("2026-08-03", "Globe", "11:00", "Marcus"),
    ])
    img = tmp_path / "pip.png"
    img.write_bytes(b"x")
    config = formmodel.build_config(
        project_name="MyEvent {date}", frame_rate="25", width=1920, height=1080,
        default_session_minutes=90, drives={"Globe": "REC_GLOBE_01"},
        assets=[{"path": str(img), "bin": "Backgrounds", "theatre": "Globe"}],
    )
    log = io.StringIO()
    result = execute(rows, config, dry_run=True, recipe_out=str(tmp_path),
                     log=lambda m: log.write(str(m) + "\n"))
    out = log.getvalue()
    assert result.plan.project_name == "MyEvent 2026-08-03"
    assert "Globe" in out and "09-30 - Alice" in out
    # theatre-scoped asset nested under the theatre's Assets bin
    globe = next(n for n in result.plan.root_children if n.name == "Globe")
    globe_assets = next(c for c in globe.children if c.name == "Assets")
    assert any(c.name == "Backgrounds" for c in globe_assets.children)
