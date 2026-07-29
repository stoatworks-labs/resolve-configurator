# AGENTS.md — bringing an LLM up to speed on Resolve Configurator

Orientation for an AI assistant (or a new human) picking this project up cold. There is no
`CLAUDE.md` here; this is the entry point.

---

## 1. What this is

A Python tool that **scaffolds a DaVinci Resolve project for a multi-theatre event** — from
the *same session CSV* that the `nc-filedropbatch` Nextcloud app uses to collect presenter
uploads.

Point it at a sessions list plus a small config (frame rate, resolution, record-drive map,
asset manifest) and it builds the project format, theatre/day bins, per-session timelines,
asset imports and smart-bin recipes.

Public repo. Tests and lint are green. **Renamed** from `resolve-session-builder` — if you
find that old name anywhere, it's stale.

## 2. The key architectural idea: one CSV, two tools

The point of this project is that **the same CSV drives both the upload collection and the
edit-suite setup.**

```
   session CSV
   /        \
nc-filedropbatch   resolve-configurator
(collects uploads) (builds the Resolve project)
```

That shared schema is the contract. **If you change how the CSV is interpreted here, check
`nc-filedropbatch` (a separate repo, PHP/Nextcloud app) for the other half.** Diverging on
column meaning breaks the workflow in a way neither repo's tests would catch on their own.

`csv_reader.py` is where that contract is implemented.

## 3. Layout

```
src/resolve_configurator/
  cli.py         Command-line entry point
  gui.py         Desktop UI
  config.py      Config loading (frame rate, resolution, drive map, assets)
  csv_reader.py  Session CSV parsing - the shared contract with nc-filedropbatch
  model.py       Domain model
  formmodel.py   Form/UI model
  core.py        Orchestration
  builder.py     Builds the Resolve project
  naming.py      Bin/timeline naming rules
packaging/
  build_binary.py, launcher.py
tests/           test_core, test_builder, test_csv_reader, test_model,
                 test_formmodel, test_naming, test_smartbins, test_cli_dryrun
```

`naming.py` deserves care: bin and timeline names are what the editor actually sees in
Resolve, and renaming conventions mid-project is disruptive. The naming tests encode the
agreed scheme.

## 4. Working on it

```bash
pytest tests/
```

**`test_cli_dryrun.py` is the pattern to follow.** This tool drives DaVinci Resolve through
its scripting API — an application that must be running, and whose state is not cheap to
reset. A dry-run path means the whole build can be exercised in tests without a live Resolve
instance. Keep it working, and prefer extending it over adding tests that need the real app.

## 5. Conventions

- Public repo. "Commit" means commit **and** push.
- Multi-platform release CI; cross-compile macOS x86_64 on `macos-14` — never `macos-13`.

## 6. Related

- **`nc-filedropbatch`** — the Nextcloud app at the other end of the shared CSV.

## Diagnostics

Log via `diag.log`, not `print`. `diag.init(...)` goes before anything that can fail. Tk
apps must also call `diag.install_tk_excepthook(root)` before any callback can run —
Tkinter swallows callback exceptions, so without it a fault in a button handler never
reaches the crash handler. See [docs/diagnostics.md](docs/diagnostics.md).
