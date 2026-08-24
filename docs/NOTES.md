# Notes

Working notes for this repo: status, decisions, and the traps that have actually bitten.
Migrated out of Claude Code's memory on 2026-08-24, so they are written in the first
person and dated by when each thing was learned — that date is usually the useful part.

Cross-cutting notes that are not specific to this repo live in
[fleet-notes](https://github.com/stoatworks-labs/fleet-notes).

*Python tool scaffolding a DaVinci Resolve project (bins/timelines/media/smart-bin recipes) from the nc-filedropbatch session CSV*

Python 3.11+ tool at ~/Projects/resolve-configurator (GitHub PUBLIC:
github.com/allansargeant/resolve-configurator) that turns the SAME 5-column CSV as
**nc filedropbatch** (`Date, Theatre, Start Time, presenter name, presenter email`) plus a TOML config
into a DaVinci Resolve project: sets frame rate/resolution (+ any `[project.settings]` passthrough via
Project.SetSetting), builds a media-pool bin per theatre and day, an empty timeline per session
(`Start Time - Presenter`), imports background/holding-slide assets (global or per-theatre via manifest), and
emits a per-session smart-bin **recipe** (smart-bins.md/.json). Console command: `resolve-configure`; package
`resolve_configurator`. (Originally named resolve-session-builder; renamed at first push.)

Key constraints (researched, hold as of Resolve v20/v21): the scripting API **cannot create smart bins** (hence
recipe output, not real bins) and **external CLI scripting needs Resolve Studio** (free version = in-app
Scripts menu only). Tool degrades to `--dry-run` when Resolve isn't reachable — that's also what CI runs.
Session time windows are derived (end = next session's start; last = `default_session_minutes`); record-drive
names come from a `[drives]` theatre→drive config map. Name sanitiser + dedup ported 1:1 from nc-filedropbatch
(colons/slashes replaced not stripped, so `09:30`→`09-30`; dedup on Theatre+Date+Start Time).

Also has a **Tkinter desktop GUI** (`resolve-configure-gui`, in `gui.py`): a grey-on-grey editor styled to
resemble the nc-filedropbatch page layout — editable manual sessions table (add/del/Load CSV/Export CSV),
project settings with Load/Save config (round-trips project.toml), and per-theatre asset panels to browse
Background/PiP/Slide images (+ a Global panel); Dry-run/Apply on a background thread. Form→domain conversion
lives in pure, tested `formmodel.py` (rows_from_sessions/build_config/config_to_toml). CLI and GUI share
`core.execute(rows, config, ...)`. Tagged **v0.1.0**
with a GitHub Release: wheel+sdist AND standalone PyInstaller GUI apps (macOS arm64 .app, Windows x64, Linux
x64) via `packaging/build_binary.py` + release.yml. macOS x86_64 NOT built (PyInstaller can't cross-compile,
Intel runners retired) — Intel Macs use pip. Note for future binary builds: macOS needs `--windowed --onedir`
(onefile+windowed is deprecated, .app can't be one file); zip only the `.app`.

Architecture: pure-data `Plan` (build_plan) is Resolve-free and testable; `apply_plan` walks it against a
`ResolveBackend`. stdlib-only runtime (tomllib), pytest+ruff dev, lint+test CI (3.11-3.13). 38 tests pass.
Live Resolve-apply never yet run on real hardware (no Studio in this env) — only dry-run verified. Standard AI
disclaimer in README applies (see **disclaimer scope** (working-practice note, kept in Claude memory)).
