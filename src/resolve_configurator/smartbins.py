"""Compute the smart-bin "recipe" for each session.

The Resolve scripting API cannot create smart bins (confirmed for v20/v21), so
instead of pretending to, the builder emits an exact rule set per session that
you recreate once in the Smart Bin editor. Each recipe matches the day's
recordings down to one session by:

    File Path   contains       <record drive>
    Date Created is            <session date>
    Start TC    is in the range <window start> .. <window end>

This assumes recorders are jammed to time-of-day timecode. Output is written as
human-readable Markdown and machine-readable JSON.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .model import PlannedSession


@dataclass(frozen=True)
class Criterion:
    field: str
    operator: str
    value: str | list[str]


@dataclass
class SessionRecipe:
    theatre: str
    date: str
    smart_bin_name: str
    presenter: str
    drive: str | None
    criteria: list[Criterion]
    warnings: list[str]


def build_recipes(
    planned: list[PlannedSession], drives: dict[str, str]
) -> list[SessionRecipe]:
    recipes: list[SessionRecipe] = []
    for ps in planned:
        session = ps.window.session
        drive = drives.get(ps.theatre)
        criteria: list[Criterion] = []
        warnings: list[str] = []

        if drive:
            criteria.append(Criterion("File Path", "Contains", drive))
        else:
            warnings.append(
                f"No record drive mapped for theatre {ps.theatre!r}; "
                f"add a [drives] entry to include a 'File Path Contains' rule."
            )

        if session.date_valid:
            criteria.append(Criterion("Date Created", "is", ps.date))
        else:
            warnings.append(f"Date {ps.date!r} is not YYYY-MM-DD; 'Date Created' rule omitted.")

        if ps.window.start_tc and ps.window.end_tc:
            criteria.append(
                Criterion("Start TC", "is in the range", [ps.window.start_tc, ps.window.end_tc])
            )
        else:
            warnings.append("No valid start time; timecode-range rule omitted.")

        recipes.append(
            SessionRecipe(
                theatre=ps.theatre,
                date=ps.date,
                smart_bin_name=ps.timeline_name,
                presenter=session.presenter_name,
                drive=drive,
                criteria=criteria,
                warnings=warnings,
            )
        )
    return recipes


def render_markdown(recipes: list[SessionRecipe]) -> str:
    lines: list[str] = [
        "# Smart-bin recipes",
        "",
        "The DaVinci Resolve scripting API can't create smart bins, so create these by hand once:",
        "**Media Pool → right-click Smart Bins → Add Smart Bin**, match **All** of the rules, and",
        "name the bin as shown. Rules assume recorders use **time-of-day timecode**.",
        "",
    ]
    # group by theatre -> date
    by_theatre: dict[str, dict[str, list[SessionRecipe]]] = {}
    for r in recipes:
        by_theatre.setdefault(r.theatre or "(no theatre)", {}).setdefault(r.date, []).append(r)

    for theatre in sorted(by_theatre):
        lines.append(f"## {theatre}")
        lines.append("")
        for date in sorted(by_theatre[theatre]):
            lines.append(f"### {date}")
            lines.append("")
            for r in by_theatre[theatre][date]:
                presenter = r.presenter or "no presenter"
                lines.append(f"**Smart bin:** `{r.smart_bin_name}`  ({presenter})")
                lines.append("")
                lines.append("| Field | Operator | Value |")
                lines.append("| --- | --- | --- |")
                for c in r.criteria:
                    value = " .. ".join(c.value) if isinstance(c.value, list) else c.value
                    lines.append(f"| {c.field} | {c.operator} | {value} |")
                lines.append("")
                for w in r.warnings:
                    lines.append(f"> ⚠️ {w}")
                if r.warnings:
                    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_json(recipes: list[SessionRecipe]) -> str:
    return json.dumps([asdict(r) for r in recipes], indent=2) + "\n"


def write_recipes(
    recipes: list[SessionRecipe], out_dir: str | Path
) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "smart-bins.md"
    json_path = out / "smart-bins.json"
    md_path.write_text(render_markdown(recipes), encoding="utf-8")
    json_path.write_text(to_json(recipes), encoding="utf-8")
    return md_path, json_path
