"""Build a standalone GUI binary with PyInstaller and zip it for release.

Usage: python packaging/build_binary.py <target-label>   e.g. macos-arm64

Produces release/resolve-configurator-gui-<target-label>.zip containing whatever
PyInstaller emits into dist/ (a single exe on Linux/Windows, a .app on macOS).
Cross-platform zipping is done in Python so the CI step is identical on every OS.
"""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

NAME = "resolve-configurator-gui"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_binary.py <target-label>", file=sys.stderr)
        return 2
    target = sys.argv[1]

    root = Path(__file__).resolve().parents[1]
    dist = root / "dist"
    build = root / "build"
    # Clean previous output so the zip only contains this run's artifact.
    for path in (dist, build):
        shutil.rmtree(path, ignore_errors=True)

    system = platform.system()
    args = [
        str(root / "packaging" / "launcher.py"),
        "--name", NAME,
        "--noconfirm",
        "--clean",
        "--distpath", str(dist),
        "--workpath", str(build),
        "--specpath", str(build),
    ]
    if system == "Darwin":
        # A macOS .app is a directory bundle, so onefile can't apply; --windowed
        # onedir produces dist/<name>.app.
        args += ["--windowed", "--onedir"]
    elif system == "Windows":
        # Single no-console .exe.
        args += ["--windowed", "--onefile"]
    else:  # Linux — plain single executable.
        args += ["--onefile"]

    PyInstaller.__main__.run(args)

    out = root / "release"
    out.mkdir(exist_ok=True)
    archive = out / f"{NAME}-{target}"
    if system == "Darwin":
        # Ship only the .app bundle (onedir also leaves a raw folder in dist/).
        shutil.make_archive(str(archive), "zip", root_dir=str(dist), base_dir=f"{NAME}.app")
    else:
        shutil.make_archive(str(archive), "zip", root_dir=str(dist))
    print(f"wrote {archive.with_suffix('.zip')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
