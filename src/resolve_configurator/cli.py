"""Command-line entry point: build a Resolve project from a session CSV."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import ConfigError, load_config
from .core import execute
from .csv_reader import CsvError, read_csv
from .resolve_api import ResolveError


def run(
    csv_path: str,
    config_path: str,
    *,
    dry_run: bool = False,
    project_name: str | None = None,
    recipe_out: str = ".",
    log=print,
) -> int:
    """Load inputs, then build the plan and apply/dry-run via the shared core."""
    rows = read_csv(csv_path)
    config = load_config(config_path)
    if project_name:
        config.project_name = project_name
    execute(rows, config, dry_run=dry_run, recipe_out=recipe_out, log=log)
    return 0


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
