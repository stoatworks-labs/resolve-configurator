"""Command-line entry point: build a Resolve project from a session CSV."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import ConfigError, load_config
from .core import execute
from .csv_reader import CsvError, read_csv
from .resolve_api import ResolveError
from . import diag


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


DIAG_APP = "resolve-configurator"
DIAG_ENV_PREFIX = "RESOLVE_CONFIGURATOR"


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)

    # Handled before argparse, deliberately: the real parser requires a CSV and
    # a config file, and someone asking for diagnostics has just had a run fail
    # and has neither to hand.
    if "--collect-diagnostics" in raw:
        diag.init(app=DIAG_APP, env_prefix=DIAG_ENV_PREFIX, version=__version__)
        # stdout, so it can be used in a script; logging went to stderr.
        print(diag.collect_diagnostics())
        return 0

    args = build_parser().parse_args(argv)

    # Before anything that can fail, so a failure is logged and captured.
    diag.init(app=DIAG_APP, env_prefix=DIAG_ENV_PREFIX,
              version=__version__, config=vars(args))

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
