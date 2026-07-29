# Resolve Configurator — Interfaces

The CLI, the TOML config schema, the shared session CSV, and the smart-bin recipe output.

| § | Interface | Source |
|---|---|---|
| [1](#1-cli) | CLI | `cli.py` |
| [2](#2-project-toml) | Project TOML | `config.py`, `project.example.toml` |
| [3](#3-the-session-csv-contract) | The session CSV | `csv_reader.py` |
| [4](#4-naming-rules) | Naming rules | `naming.py` |
| [5](#5-smart-bin-recipe-output) | Smart-bin recipe output | `builder.py` |

---

## 1. CLI

```
resolve-configure <csv> --config <toml> [--dry-run] [--project-name NAME] [--recipe-out DIR]
```

| Argument | Notes |
|---|---|
| `csv` | positional — the sessions CSV (§3) |
| `-c` / `--config` | **required** |
| `--dry-run` | **never touches Resolve.** Prints the planned structure and writes the recipes. |
| `--project-name` | overrides `[project].name` |
| `--recipe-out` | directory for `smart-bins.md` / `.json` (default: current directory) |
| `--version` | |

**`--dry-run` still writes the recipe files.** It is a "don't touch Resolve" flag, not a
"produce nothing" flag — which makes it the normal way to get the smart-bin rules without
building anything.

**External CLI use requires DaVinci Resolve *Studio***; external scripting is a Studio feature.
The free version can only run this from Resolve's own **Workspace → Scripts** menu. There's also
a desktop GUI (`gui.py`). See the README for all three routes.

---

## 2. Project TOML

Full annotated example in [`project.example.toml`](../project.example.toml). **Relative asset
paths resolve relative to the config file's directory**, not the working directory.

### `[project]`

| Key | Notes |
|---|---|
| `name` | **`{date}` expands to the earliest session date in the CSV** (`YYYY-MM-DD`) |
| `create_if_missing` | |
| `use_current` | build into the currently-open project instead of creating one |

### `[project.format]`

`frame_rate` is a **string**, using Resolve's own values (`"24"`, `"25"`, `"23.976"`, …) — not a
number. Plus `width` and `height`.

### `[project.settings]` — the escape hatch

**Every key/value here is applied verbatim via `Project.SetSetting()`**, so any Resolve project
setting can be set without a code change. **Values are stringified.**

That also means **nothing validates them**: a misspelled key or an invalid value is passed
straight to Resolve, which will typically ignore it silently. If a setting didn't take, check
the spelling against Resolve's own setting names first.

### `[sessions]`

| Key | Notes |
|---|---|
| `default_session_minutes` | **Only used for the last session of each theatre-day** — see below |
| `timeline_name_template` | fields `{start}` `{presenter}` `{theatre}` `{date}`; collisions auto-disambiguated by appending `[theatre date]` |

> **Session windows are derived, not read from the CSV.** A session ends **when the next one on
> the same theatre + day starts.** Only the **last** session of each theatre-day has no "next",
> and that one gets `default_session_minutes`.
>
> So a gap in the schedule becomes part of the preceding session's window, and
> `default_session_minutes` affects exactly one session per theatre per day.

### `[drives]`

Theatre → record drive name, used in the smart-bin recipe's *File Path contains* rule.

**A theatre not listed still gets bins and timelines** — its recipe just omits the drive rule,
and the run warns.

### `[[assets]]`

One entry per file imported into a media-pool bin:

```toml
[[assets]]
path = "assets.example/slides/holding.png"
scope = "global"        # -> Assets/<bin>
bin = "Slides"

[[assets]]
path = "assets.example/slides/globe-title.png"
theatre = "Globe"       # scope is implied "theatre" -> Globe/Assets/<bin>
bin = "Slides"
```

Setting `theatre` implies `scope = "theatre"`.

---

## 3. The session CSV contract

> **The same CSV drives this tool and
> [nc-filedropbatch](https://github.com/stoatworks-labs/nc-filedropbatch)**, the Nextcloud app that
> collects presenter uploads for the same event.
>
> ```
>          session CSV
>          /         \
> nc-filedropbatch    resolve-configurator
> (collects uploads)  (builds the Resolve project)
> ```
>
> **If you change how the CSV is interpreted here, check `nc-filedropbatch` for the other half.**
> Diverging on column meaning breaks the workflow in a way neither repo's tests would catch.

Five columns:

```
Date, Theatre, Start Time, presenter name, presenter email
```

`csv_reader.py`'s semantics are **ported from nc-filedropbatch's `CsvReader.php`** so both tools
accept exactly the same files:

- headers matched **case-insensitively after trimming**;
- a **UTF-8 BOM** on the first header is tolerated (`utf-8-sig`);
- **every value trimmed**;
- **fully-blank lines skipped**;
- **a missing required column is a hard error** (`CsvError`) — nothing is built.

`parse_rows()` accepts already-parsed rows (e.g. a spreadsheet export), mirroring the PHP method
of the same name.

**Rows are de-duplicated on `Theatre + Date + Start Time`** — the same key nc-filedropbatch
matches on.

---

## 4. Naming rules

`naming.py` is **ported 1:1 from nc-filedropbatch's `PathSanitizer.php`**, so both tools produce
the same names from the same CSV.

`sanitize_segment()`:

- replaces `/ \ : * ? " < > |` with `-` — **replaced, not stripped**, so distinct inputs never
  collapse (`10:00` vs `1000`);
- collapses whitespace runs to a single space;
- strips leading/trailing whitespace and dots;
- empty → **`untitled`**;
- truncates to **200** characters.

So `09:30` becomes `09-30` in a bin or timeline name.

> **Bin and timeline names are what the editor actually sees in Resolve, and renaming conventions
> mid-project is disruptive.** The naming tests encode the agreed scheme — treat a change here as
> breaking.

---

## 5. Smart-bin recipe output

`smart-bins.md` (human) and `smart-bins.json` (machine), written to `--recipe-out`.

### Why a recipe rather than real smart bins

**Resolve's scripting API cannot create smart bins** — confirmed for v20/v21. You can create
regular bins, timelines and import media; **smart-bin definitions are a UI/database artifact.**
And at build time the recordings don't exist in the pool yet, so there are no clips to tag.

So the tool does everything the API *can* do and emits the exact rules to recreate each smart bin
**once, by hand**.

### The rules per session

| Field | Operator | Value |
|---|---|---|
| File Path | Contains | the record drive for that theatre |
| Date Created | is | the session date |
| Start TC | is in the range | session start … session end |

> **⚠ The timecode rules assume recorders are jammed to time-of-day timecode.** If they aren't,
> the Start TC rule will match nothing, and the smart bin will look empty for reasons that have
> nothing to do with this tool.

The window is derived as described in §2.

### Rows that don't fully parse still produce output

- **An unparseable start time** still gets a timeline, named from the **raw value** — it just
  gets **no timecode rule** in the recipe.
- **A missing theatre** produces an **`untitled`** bin.
- **A theatre with no drive mapping** gets a recipe with **no File Path rule**.

All three are reported in the run summary rather than failing the build. **Read the summary** —
a recipe missing its drive or timecode rule looks complete until you use it.

### Re-running is safe

Bins are **found-or-created**, and timelines already present are **skipped by name**. Running
again after adding sessions to the CSV adds only what's new.

---

## See also

- [USER-GUIDE.md](USER-GUIDE.md) — running it, and what to check
- [DEVELOPING.md](DEVELOPING.md) — the dry-run pattern and the shared contract
- [README](../README.md) — the three ways to run it, install, requirements
