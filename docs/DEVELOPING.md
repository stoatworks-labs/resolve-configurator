# Resolve Configurator — Developing

Python 3.11+, no third-party runtime dependencies (stdlib `tomllib`). Tests and lint are green.

**Renamed** from `resolve-session-builder` — if you find that old name anywhere, it's stale.

---

## 1. The key architectural idea: one CSV, two tools

The point of this project is that **the same CSV drives both the upload collection and the
edit-suite setup.**

```
         session CSV
         /         \
nc-filedropbatch    resolve-configurator
(collects uploads)  (builds the Resolve project)
```

**That shared schema is the contract.**

> **If you change how the CSV is interpreted here, check
> [`nc-filedropbatch`](https://github.com/allansargeant/nc-filedropbatch) — a separate repo, a
> PHP/Nextcloud app — for the other half.** Diverging on column meaning breaks the workflow in a
> way **neither repo's tests would catch on their own.**

Two modules are deliberate ports, and both say so in their docstrings:

- **`csv_reader.py`** — semantics ported from `CsvReader.php`, so both tools accept exactly the
  same files (case-insensitive headers, BOM tolerated, values trimmed, blank lines skipped,
  missing column is a hard error). `parse_rows()` mirrors the PHP method of the same name.
- **`naming.py`** — ported **1:1** from `PathSanitizer.php`, so both produce the same names from
  the same CSV. Forbidden characters are **replaced, not stripped**, so distinct inputs never
  collapse into one name.

Keeping those two in step is the whole value of the pairing. Changing either is a two-repo
change.

---

## 2. Working on it

```bash
pip install -e '.[dev]'
pytest -q          # unit + dry-run tests, no Resolve needed
ruff check .
```

Tests: `test_core`, `test_builder`, `test_csv_reader`, `test_model`, `test_formmodel`,
`test_naming`, `test_smartbins`, `test_cli_dryrun`.

### `test_cli_dryrun.py` is the pattern to follow

This tool drives DaVinci Resolve through its scripting API — **an application that must be
running, and whose state is not cheap to reset.**

**A dry-run path means the whole build can be exercised in tests without a live Resolve
instance.** Keep it working, and **prefer extending it over adding tests that need the real
app.** A test suite that requires Resolve running is a suite that stops being run.

Note that `--dry-run` still **writes the recipe files** — it's "don't touch Resolve", not
"produce nothing". That's what makes it testable end to end.

---

## 3. Layout

```
src/resolve_configurator/
  cli.py         Command-line entry point
  gui.py         Desktop UI
  config.py      Config loading (frame rate, resolution, drive map, assets)
  csv_reader.py  Session CSV parsing — the shared contract with nc-filedropbatch
  model.py       Domain model
  formmodel.py   Form/UI model
  core.py        Orchestration
  builder.py     Builds the Resolve project
  naming.py      Bin/timeline naming rules
packaging/
  build_binary.py, launcher.py
tests/
```

---

## 4. `naming.py` deserves care

**Bin and timeline names are what the editor actually sees in Resolve, and renaming conventions
mid-project is disruptive.** The naming tests encode the agreed scheme.

Treat a change to `sanitize_segment()` as breaking: it changes every name the tool has ever
produced, desynchronises this repo from nc-filedropbatch, and lands on an editor who has already
learned the old ones.

The 200-character truncation and the `untitled` fallback are part of that scheme, not incidental.

---

## 5. Behaviours that are deliberate, not gaps

Don't "fix" these without a reason:

- **Resolve's scripting API cannot create smart bins** (confirmed v20/v21) — they're a
  UI/database artifact, and at build time there are no clips in the pool to tag anyway. Hence the
  `smart-bins.md` / `.json` recipe. There is no API call to find.
- **Session windows are derived**: a session ends when the next on that theatre-day starts, and
  only the last of each theatre-day uses `default_session_minutes`.
- **Imperfect rows still produce output.** An unparseable start time gets a timeline named from
  the raw value (and no timecode rule); a missing theatre gets an `untitled` bin; an unmapped
  theatre gets a recipe without a File Path rule. **All are reported in the run summary** — keep
  populating it, because those gaps are invisible in the output itself.
- **Re-running is idempotent-ish by design**: bins are found-or-created and existing timelines
  are skipped by name.
- **`[project.settings]` is an unvalidated verbatim passthrough** to `Project.SetSetting()`. That
  is deliberate — it lets any Resolve setting be set without a code change — and it means typos
  fail silently. Don't add a whitelist without losing that property knowingly.

---

## 6. Conventions

- Public repo. "Commit" means commit **and** push.
- Multi-platform release CI; **cross-compile macOS x86_64 on `macos-14` — never `macos-13`.**

---

## See also

- [API.md](API.md) — CLI, TOML schema, CSV contract, recipe format
- [USER-GUIDE.md](USER-GUIDE.md) — the operator view
- [`AGENTS.md`](../AGENTS.md) — LLM onboarding
