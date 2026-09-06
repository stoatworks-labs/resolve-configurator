"""Build a standalone GUI binary with PyInstaller and zip it for release.

Usage: python packaging/build_binary.py <target-label>   e.g. macos-arm64

Produces release/resolve-configurator-gui-<target-label>.zip containing whatever
PyInstaller emits into dist/ (a single exe on Linux/Windows, a .app on macOS).
Cross-platform zipping is done in Python so the CI step is identical on every OS.
"""

from __future__ import annotations

import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import PyInstaller.__main__

NAME = "resolve-configurator-gui"



def _package_version(root: Path) -> str:
    """The version the package declares, for stamping into the .app.

    Read out of the source rather than via importlib.metadata so a build from a
    checkout that has not been reinstalled still stamps the version the code
    going into the bundle actually carries. `__init__.py` is the one place the
    version is written down -- pyproject.toml reads it from there too, through
    [tool.setuptools.dynamic] -- so there is nothing else to keep in step.
    """
    src = root / "src" / "resolve_configurator" / "__init__.py"
    found = re.search(r'^__version__\s*=\s*"([^"]+)"', src.read_text(encoding="utf-8"), re.M)
    if not found:
        raise SystemExit(f"{src}: no __version__ to stamp into the bundle.")
    return found.group(1)


def _stamp_version(app: Path, version: str) -> None:
    """Write the real version into the .app's Info.plist.

    PyInstaller has no CLI flag for the macOS bundle version -- `--version-file`
    is Windows-only -- so with no .spec file it writes its own default:
    `CFBundleShortVersionString = 0.0.0`, and no CFBundleVersion at all. The
    DMG and PKG wrapped around the app are named and stamped correctly by
    release-lib from the tag, which is exactly why this went unnoticed for five
    releases: everything except the bundle itself was right.

    It matters because that plist is what anything on the user's machine reads
    to find out which version is installed. Burrow reads CFBundleVersion (then
    the short string) and ranks it above its own install ledger, so every copy
    of this app reported "0.0.0, update available" against the very version
    Burrow had just installed -- and reinstalling could not clear it, because
    the replacement bundle said 0.0.0 too.

    Both keys are set, to the same value, which is what every other bundle in
    the fleet carries. Called before the app is zipped and before CI signs it,
    so the zip, the installers and the signature all seal the corrected plist.
    """
    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as fh:
        info = plistlib.load(fh)
    info["CFBundleVersion"] = version
    info["CFBundleShortVersionString"] = version
    with plist_path.open("wb") as fh:
        plistlib.dump(info, fh)

    # Proving it took, in the same spirit as the symlink guard below: shipping
    # 0.0.0 a second time should fail this build, not the next person's update
    # check.
    with plist_path.open("rb") as fh:
        written = plistlib.load(fh)
    if written.get("CFBundleVersion") != version:
        raise SystemExit(
            f"{plist_path}: version did not stick -- CFBundleVersion is "
            f"{written.get('CFBundleVersion')!r}, expected {version!r}."
        )


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
        app = dist / f"{NAME}.app"
        # Before the zip, so the zip, and the DMG and PKG that CI wraps around
        # the same dist/ app afterwards, all carry the real version.
        _stamp_version(app, _package_version(root))
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
             str(app), str(zip_path)],
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
