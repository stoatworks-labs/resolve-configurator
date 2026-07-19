"""Command-line entry point: build a Resolve project from a session CSV."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .builder import apply_plan, build_plan, render_plan
from .config import ConfigError, load_config
from .csv_reader import CsvError, read_csv
from .model import build_show
from .resolve_api import ResolveError, connect
from .smartbins import build_recipes, write_recipes


def run(
    csv_path: str,
    config_path: str,
    *,
    dry_run: bool = False,
    project_name: str | None = None,
    recipe_out: str = ".",
    log=print,
) -> int:
    """Build the plan, write recipes, and either apply to Resolve or dry-run."""
    rows = read_csv(csv_path)
    config = load_config(config_path)
    if project_name:
        config.project_name = project_name

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
    else:
        apply_plan(plan, backend, log=log)
        log(f"Applied to project: {plan.project_name}")

    log(f"\nSmart-bin recipe written to:\n  {md_path}\n  {json_path}")
    _report(show, plan, log)
    return 0


def _report(show, plan, log) -> None:
    n_sessions = len(plan.planned_sessions)
    n_theatres = len(show.theatres)
    log(f"\nSummary: {n_sessions} session(s) across {n_theatres} theatre(s).")
    if show.duplicates:
        log(f"  {len(show.duplicates)} duplicate row(s) dropped (same Theatre+Date+Start Time).")
    if show.invalid_time:
        rows = ", ".join(str(s.row_number) for s in show.invalid_time)
        log(f"  {len(show.invalid_time)} row(s) with unparseable start time (rows {rows}): "
            f"timeline created, no timecode rule.")
    for w in plan.warnings:
        log(f"  ! {w}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resolve-configure",
        description="Scaffold a DaVinci Resolve project (bins, timelines, media, "
        "smart-bin recipes) from a theatre/session CSV.",
    )
    parser.add_argument("csv", help="Path to the sessions CSV.")
    parser.add_argument(
        "-c", "--config", required=True, help="Path to the project TOML config."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Never touch Resolve; print the planned structure and write recipes.",
    )
    parser.add_argument(
        "--project-name", help="Override [project].name from the config."
    )
    parser.add_argument(
        "--recipe-out",
        default=".",
        help="Directory for smart-bins.md / smart-bins.json (default: current dir).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(
            args.csv,
            args.config,
            dry_run=args.dry_run,
            project_name=args.project_name,
            recipe_out=args.recipe_out,
        )
    except (CsvError, ConfigError, ResolveError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
