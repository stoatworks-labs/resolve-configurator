# Resolve Configurator

> **AI-assisted project.** This codebase was created with [Claude Code](https://claude.com/claude-code)
> (Anthropic), directed and reviewed by a human author — including the code, the docs, and the config.
> Review it yourself before relying on it in production, same as you would for any code.

Scaffold a **DaVinci Resolve** project for a multi-theatre event from the *same CSV* the
[nc-filedropbatch](https://github.com/allansargeant/nc-filedropbatch) Nextcloud app uses to collect presenter
uploads. Point it at your sessions list plus a small config (frame rate, resolution, record-drive map, asset
manifest) and it builds:

- the **project format** — frame rate, resolution, and any other project setting you name;
- a **media-pool bin per theatre and per day** (`Theatre / Date`);
- an **empty timeline per session** inside each day's bin (`Start Time - Presenter`);
- prepopulated **backgrounds** (for PiP looks) and **holding/title slides**, global or per-theatre;
- a **smart-bin recipe** — the exact rule set to filter each day's recordings down to one session, by record
  drive, date, and timecode window.

The input CSV is unchanged from nc-filedropbatch:

```
Date, Theatre, Start Time, presenter name, presenter email
```

so the same show file drives both the upload side (Nextcloud) and the edit side (Resolve).

## Why a "recipe" and not real smart bins?

DaVinci Resolve's scripting API **cannot create smart bins** (confirmed for v20/v21 — you can create regular
bins, timelines, and import media, but smart-bin definitions are a UI/database artifact). And at build time the
recordings don't exist in the pool yet, so there are no clips to tag. So the tool builds everything the API
*can* do and writes a `smart-bins.md` / `smart-bins.json` with the precise rules to recreate each smart bin
once, by hand. Each session's rules are:

| Field | Operator | Value |
| --- | --- | --- |
| File Path | Contains | *record drive for the theatre* |
| Date Created | is | *session date* |
| Start TC | is in the range | *session start .. session end* |

The timecode window is **derived**: a session ends when the next one on that theatre/day starts; the last
session of the day uses `default_session_minutes`. Rules assume recorders are jammed to **time-of-day timecode**.

## Requirements

- **Python 3.11+** (uses the stdlib `tomllib`; no third-party runtime dependencies).
- **DaVinci Resolve Studio** to apply a build to Resolve. External scripting is a *Studio* feature — the free
  version can only run scripts from Resolve's own **Workspace → Scripts** menu/Console.
- No Resolve at all is needed for `--dry-run`, which prints the full plan and still writes the recipe.

## Install

```
pip install -e .
```

## Use — external CLI (Studio)

```
resolve-configure sessions.csv --config project.toml
```

With Resolve running, this creates/loads the project, applies the settings, builds the bins/timelines, imports
the assets, and writes the recipe. Flags:

- `--dry-run` — never touch Resolve; print the planned tree and write the recipe. **Start here.**
- `--project-name NAME` — override `[project].name` from the config.
- `--recipe-out DIR` — where to write `smart-bins.md` / `smart-bins.json` (default: current dir).

Try it now, no Resolve needed:

```
resolve-configure sample-sessions.csv --config project.example.toml --dry-run --recipe-out out
```

## Use — desktop GUI

```
resolve-configure-gui
```

A small Tkinter window: pick the CSV and config, adjust the common settings (project name, frame rate,
resolution, default session length), then **Dry run** to preview the plan tree or **Apply to Resolve** to build
it. The output pane shows exactly what the CLI would print. Everything except the actual apply works with no
Resolve installed, so you can prepare and preview a show anywhere. Needs Tk (bundled with python.org builds; on
Homebrew Python install `python-tk`).

## Use — in-app Scripts menu (free or Studio)

The same code runs from inside Resolve. Make the `resolve_configurator` package importable on Resolve's
Python path, then drop a one-line launcher into Resolve's Scripts folder:

```python
from resolve_configurator import scripts_menu
scripts_menu.main()
```

It reads its inputs from environment variables (with sensible fallbacks):

| Variable | Meaning | Default |
| --- | --- | --- |
| `RC_CSV` | sessions CSV | `sessions.csv` next to the package |
| `RC_CONFIG` | project TOML | `project.toml` next to the package |
| `RC_RECIPE_OUT` | recipe output dir | alongside the CSV |

## Configuration

See [`project.example.toml`](project.example.toml) for a fully-commented example. Highlights:

- `[project.format]` — `frame_rate`, `width`, `height`.
- `[project.settings]` — an **optional passthrough**: every key here is applied verbatim via
  `Project.SetSetting()`, so you can set *any* project setting (colour science, monitor format, …) without a
  code change.
- `[drives]` — `Theatre = "RECORD_DRIVE_NAME"`, used in the smart-bin recipe.
- `[[assets]]` — one entry per file to import; `scope = "global"` → `Assets/<bin>`, or `theatre = "Globe"` →
  `Globe/Assets/<bin>`.

## Behaviour notes

- Rows are de-duplicated on `Theatre + Date + Start Time` (the same key nc-filedropbatch matches on).
- Bin/timeline names use the same sanitiser as nc-filedropbatch — forbidden characters like `:` and `/` are
  *replaced* (not stripped), so `09:30` becomes `09-30` and distinct inputs never collide.
- Rows with an unparseable start time still get a timeline (named from the raw value); they just get no
  timecode rule in the recipe. Missing theatre → an `untitled` bin. All of this is reported in the run summary.
- Re-running against an existing project is safe: bins are found-or-created and timelines already present are
  skipped by name.

## Development

```
pip install -e '.[dev]'
pytest -q          # unit + dry-run tests, no Resolve needed
ruff check .
```

## License

MIT.
