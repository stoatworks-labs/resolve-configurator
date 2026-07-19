"""In-app entry point for DaVinci Resolve's Workspace -> Scripts menu.

Resolve runs a menu script with no arguments, so this shim reads its inputs from
environment variables (fall back to files next to this script):

    RC_CSV        path to the sessions CSV   (default: ./sessions.csv)
    RC_CONFIG     path to the project TOML    (default: ./project.toml)
    RC_RECIPE_OUT output dir for recipes      (default: alongside the CSV)

To install: copy the whole ``resolve_configurator`` package somewhere on the
Resolve Python path (or keep it importable), then drop a tiny launcher into
Resolve's Scripts folder that does ``from resolve_configurator import scripts_menu``.
"""

from __future__ import annotations

import os
from pathlib import Path

from .cli import run


def _resolve_default(name: str, fallback: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    here = Path(__file__).resolve().parent
    return str(here / fallback)


def main() -> int:
    csv_path = _resolve_default("RC_CSV", "sessions.csv")
    config_path = _resolve_default("RC_CONFIG", "project.toml")
    recipe_out = os.environ.get("RC_RECIPE_OUT") or str(Path(csv_path).resolve().parent)
    return run(csv_path, config_path, recipe_out=recipe_out)


# Running from the Scripts menu executes the module body.
if __name__ == "__main__" or __name__ == "<run_path>":
    main()
