"""Build a standalone GUI binary with PyInstaller and zip it for release.

Usage: python packaging/build_binary.py <target-label>   e.g. macos-arm64

Produces release/resolve-configurator-gui-<target-label>.zip containing whatever
PyInstaller emits into dist/ (a single exe on Linux/Windows, a .app on macOS).
Cross-platform zipping is done in Python so the CI step is identical on every OS.
"""

from __future__ import annotations

import platform
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import PyInstaller.__main__

NAME = "resolve-configurator-gui"



def _assert_symlinks_survived(zip_path: Path) -> None:
    """Fail the build if the macOS .app came out symlink-flattened.

    The bug this guards was not caught by anything: `shutil.make_archive`
    follows symlinks and stores copies, so `Python.framework/Versions/Current`
    arrives as a *directory*. The zip is valid, the app launches from Finder,
    and only `codesign` objects -- with "bundle format unrecognized, invalid, or
    unsuitable", naming the framework rather than the zip. That shipped in
    v0.1.2 and could not be signed after the fact, because by then the structure
    was already gone.

    A zip records the unix mode in the top 16 bits of `external_attr`, so
    whether a symlink survived is readable without extracting anything.
    """
    with zipfile.ZipFile(zip_path) as archive:
        entries = archive.infolist()
        links = [e for e in entries
                 if stat.S_ISLNK(e.external_attr >> 16)]
        flattened = [e.filename for e in entries
                     if "/Versions/Current/" in e.filename]

    if flattened:
        raise SystemExit(
            f"{zip_path.name}: Versions/Current was stored as a real directory "
            f"({len(flattened)} entries under it) -- the framework has been "
            f"symlink-flattened and codesign will reject the app. "
            f"Zip it with ditto, not shutil.make_archive."
        )
    if not links:
        raise SystemExit(
            f"{zip_path.name}: contains no symlinks at all. A PyInstaller .app "
            f"is full of them, so this bundle has been flattened and codesign "
            f"will reject it."
        )


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
        # ditto, not shutil.make_archive: make_archive FOLLOWS symlinks and
        # stores copies, which silently destroys the .app. PyInstaller's bundle
        # is full of them — Python.framework/Versions/Current, the top-level
        # Python and Resources, base_library.zip — and a copy-flattened
        # framework is both several MB larger and structurally invalid, so
        # codesign rejects the whole app with "bundle format unrecognized".
        # That shipped in v0.1.2 and could not be signed after the fact.
        zip_path = archive.with_suffix(".zip")
        zip_path.unlink(missing_ok=True)
        subprocess.run(
            ["ditto", "-c", "-k", "--keepParent", "--sequesterRsrc",
             str(dist / f"{NAME}.app"), str(zip_path)],
            check=True,
        )
        # Proving it worked is the point: the flattened bundle is a valid zip
        # that launches, so nothing downstream notices until codesign.
        _assert_symlinks_survived(zip_path)
    else:
        shutil.make_archive(str(archive), "zip", root_dir=str(dist))
    print(f"wrote {archive.with_suffix('.zip')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
