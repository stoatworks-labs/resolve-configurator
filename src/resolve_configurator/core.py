"""Shared execution core used by both the CLI and the GUI.

Given already-loaded rows + config, build the plan, write the smart-bin recipe,
and either apply to Resolve or fall back to a dry run. Kept UI-agnostic: all
progress goes through the ``log`` callable, and the outcome is returned as a
``Result`` for callers that want it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .builder import Plan, apply_plan, build_plan, render_plan
from .model import Show, build_show
from .resolve_api import connect
from .smartbins import build_recipes, write_recipes


@dataclass
class Result:
    show: Show
    plan: Plan
    md_path: Path
    json_path: Path
    applied: bool  # True if changes were applied to Resolve, False if dry run


def execute(rows, config, *, dry_run: bool, recipe_out: str = ".", log=print) -> Result:
    """Run the build against a loaded config. Never raises for a missing Resolve."""
    show = build_show(rows, config.default_session_minutes)
    plan = build_plan(show, config)

    recipes = build_recipes(plan.planned_sessions, config.drives)
    md_path, json_path = write_recipes(recipes, recipe_out)

    backend = None if dry_run else connect()
    if backend is None:
        if not dry_run:
            log(
                "DaVinci Resolve not reachable — showing a dry run instead.\n"
                "(External scripting needs Resolve Studio and a running Resolve; "
                "or run this from Resolve's Scripts menu.)\n"
            )
        log(render_plan(plan))
        applied = False
    else:
        apply_plan(plan, backend, log=log)
        log(f"Applied to project: {plan.project_name}")
        applied = True

    log(f"\nSmart-bin recipe written to:\n  {md_path}\n  {json_path}")
    _report(show, plan, log)
    return Result(show=show, plan=plan, md_path=md_path, json_path=json_path, applied=applied)


def _report(show: Show, plan: Plan, log) -> None:
    n_sessions = len(plan.planned_sessions)
    n_theatres = len(show.theatres)
    log(f"\nSummary: {n_sessions} session(s) across {n_theatres} theatre(s).")
    if show.duplicates:
        log(f"  {len(show.duplicates)} duplicate row(s) dropped (same Theatre+Date+Start Time).")
    if show.invalid_time:
        rows = ", ".join(str(s.row_number) for s in show.invalid_time)
        log(
            f"  {len(show.invalid_time)} row(s) with unparseable start time (rows {rows}): "
            f"timeline created, no timecode rule."
        )
    for w in plan.warnings:
        log(f"  ! {w}")
