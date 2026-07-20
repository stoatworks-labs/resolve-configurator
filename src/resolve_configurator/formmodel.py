"""Pure form → domain conversion for the GUI (no Tkinter, fully testable).

The editor holds sessions as a list of plain dicts and assets as a list of
``{path, bin, theatre}`` dicts. These helpers turn that widget state into the
same ``rows``/``Config`` the CLI produces, plus a TOML serialiser so a show
built in the GUI round-trips to the command line.
"""

from __future__ import annotations

from pathlib import Path

from .config import DEFAULT_TIMELINE_TEMPLATE, Config

# canonical session keys, in column order
SESSION_KEYS = ["date", "theatre", "start time", "presenter name", "presenter email"]


def rows_from_sessions(sessions: list[dict]) -> list[dict]:
    """Table rows -> canonical CSV-style rows (matches csv_reader.read_csv output)."""
    out: list[dict] = []
    for i, session in enumerate(sessions, start=2):  # header would be row 1
        values = {key: str(session.get(key, "")).strip() for key in SESSION_KEYS}
        if all(v == "" for v in values.values()):
            continue  # skip fully-blank rows, like the CSV reader
        out.append({"_row_number": str(i), **values})
    return out


def distinct_theatres(rows: list[dict]) -> list[str]:
    """Non-empty theatre labels in first-seen order (drives the asset panels)."""
    seen: list[str] = []
    for row in rows:
        theatre = str(row.get("theatre", "")).strip()
        if theatre and theatre not in seen:
            seen.append(theatre)
    return seen


def build_config(
    *,
    project_name: str,
    frame_rate: str,
    width: int,
    height: int,
    default_session_minutes: int,
    drives: dict[str, str],
    assets: list[dict],
    settings: dict[str, str] | None = None,
    create_if_missing: bool = True,
    use_current: bool = False,
    timeline_name_template: str = DEFAULT_TIMELINE_TEMPLATE,
) -> Config:
    """Assemble a Config straight from form values (no TOML file involved)."""
    from .config import AssetSpec

    spec_list: list[AssetSpec] = []
    for asset in assets:
        path = Path(str(asset["path"]))
        theatre = asset.get("theatre") or None
        spec_list.append(
            AssetSpec(
                path=path,
                bin=str(asset.get("bin", "Assets")),
                theatre=str(theatre) if theatre else None,
                missing=not path.exists(),
            )
        )

    return Config(
        project_name=project_name or "Resolve Session Build {date}",
        create_if_missing=create_if_missing,
        use_current=use_current,
        frame_rate=str(frame_rate or "25"),
        width=int(width),
        height=int(height),
        settings=dict(settings or {}),
        default_session_minutes=int(default_session_minutes),
        timeline_name_template=timeline_name_template,
        drives={k: v for k, v in drives.items() if k and v},
        assets=spec_list,
    )


# --------------------------------------------------------------------------- #
# TOML serialisation (Save config) — stdlib has no writer, so emit it by hand.
# --------------------------------------------------------------------------- #

def _basic_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def config_to_toml(config: Config) -> str:
    """Serialise a Config back to the project.toml shape the CLI accepts."""
    lines: list[str] = [
        "[project]",
        f"name = {_basic_string(config.project_name)}",
        f"create_if_missing = {str(config.create_if_missing).lower()}",
        "",
        "[project.format]",
        f"frame_rate = {_basic_string(config.frame_rate)}",
        f"width = {config.width}",
        f"height = {config.height}",
        "",
    ]

    if config.settings:
        lines.append("[project.settings]")
        for key, value in config.settings.items():
            lines.append(f"{_basic_string(key)} = {_basic_string(value)}")
        lines.append("")

    lines += [
        "[sessions]",
        f"default_session_minutes = {config.default_session_minutes}",
        f"timeline_name_template = {_basic_string(config.timeline_name_template)}",
        "",
    ]

    if config.drives:
        lines.append("[drives]")
        for theatre, drive in config.drives.items():
            lines.append(f"{_basic_string(theatre)} = {_basic_string(drive)}")
        lines.append("")

    for spec in config.assets:
        lines.append("[[assets]]")
        lines.append(f"path = {_basic_string(str(spec.path))}")
        lines.append(f"bin = {_basic_string(spec.bin)}")
        if spec.theatre is None:
            lines.append('scope = "global"')
        else:
            lines.append(f"theatre = {_basic_string(spec.theatre)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
