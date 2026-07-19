"""A small Tkinter desktop front-end for the Resolve Configurator.

Pick a sessions CSV and a project TOML, tweak the common settings, then preview
the plan (Dry run) or push it to Resolve (Apply). All the real work goes through
``core.execute`` — this module is only the window around it. Everything except
the actual Resolve apply works with no Resolve installed.

Launch with ``resolve-configure-gui`` or ``python -m resolve_configurator.gui``.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .config import load_config
from .core import execute
from .csv_reader import read_csv

_DONE = object()  # sentinel pushed onto the log queue when a worker finishes


class ConfiguratorGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Resolve Configurator")
        root.minsize(640, 560)

        self.csv_var = tk.StringVar()
        self.config_var = tk.StringVar()
        self.recipe_var = tk.StringVar(value=".")
        self.project_var = tk.StringVar()
        self.frame_rate_var = tk.StringVar()
        self.width_var = tk.StringVar()
        self.height_var = tk.StringVar()
        self.minutes_var = tk.StringVar()
        self._queue: queue.Queue = queue.Queue()

        self._build()
        self._set_loaded(False)
        self.root.after(80, self._poll)

    # -- layout ----------------------------------------------------------- #
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        self._file_row(frm, 0, "Sessions CSV", self.csv_var, self._pick_csv)
        self._file_row(frm, 1, "Project config (TOML)", self.config_var, self._pick_config)
        self._file_row(frm, 2, "Recipe output dir", self.recipe_var, self._pick_recipe, dir=True)

        ttk.Button(frm, text="Load config →", command=self._load).grid(
            row=3, column=1, columnspan=2, sticky="e", **pad
        )

        box = ttk.LabelFrame(
            frm, text="Settings (loaded from config — edit before running)", padding=8
        )
        box.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)
        box.columnconfigure(1, weight=1)
        box.columnconfigure(3, weight=1)
        self._entry(box, 0, 0, "Project name", self.project_var, span=3)
        self._entry(box, 1, 0, "Frame rate", self.frame_rate_var)
        self._entry(box, 1, 2, "Default session mins", self.minutes_var)
        self._entry(box, 2, 0, "Width", self.width_var)
        self._entry(box, 2, 2, "Height", self.height_var)

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=3, sticky="ew", **pad)
        self.dry_btn = ttk.Button(btns, text="Dry run", command=lambda: self._start(dry_run=True))
        self.apply_btn = ttk.Button(
            btns, text="Apply to Resolve", command=lambda: self._start(dry_run=False)
        )
        self.dry_btn.pack(side="left")
        self.apply_btn.pack(side="left", padx=6)
        self.status = ttk.Label(btns, text="Select a CSV and config, then Load.")
        self.status.pack(side="right")

        self.output = scrolledtext.ScrolledText(frm, height=18, wrap="none", font=("Menlo", 11))
        self.output.grid(row=6, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(6, weight=1)

    def _file_row(self, parent, row, label, var, cmd, dir=False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(parent, text="Browse…", command=cmd).grid(row=row, column=2, padx=8, pady=4)

    def _entry(self, parent, row, col, label, var, span=1):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=6, pady=3)
        ttk.Entry(parent, textvariable=var).grid(
            row=row, column=col + 1, columnspan=span, sticky="ew", padx=6, pady=3
        )

    # -- pickers ---------------------------------------------------------- #
    def _pick_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Sessions CSV", filetypes=[("CSV", "*.csv"), ("All files", "*")]
        )
        if path:
            self.csv_var.set(path)
            if self.recipe_var.get() in ("", "."):
                self.recipe_var.set(str(Path(path).parent))

    def _pick_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Project config", filetypes=[("TOML", "*.toml"), ("All files", "*")]
        )
        if path:
            self.config_var.set(path)

    def _pick_recipe(self) -> None:
        path = filedialog.askdirectory(title="Recipe output directory")
        if path:
            self.recipe_var.set(path)

    # -- actions ---------------------------------------------------------- #
    def _load(self) -> None:
        csv_path, config_path = self.csv_var.get().strip(), self.config_var.get().strip()
        if not csv_path or not config_path:
            messagebox.showwarning("Missing input", "Choose both a CSV and a config file.")
            return
        try:
            config = load_config(config_path)
            rows = read_csv(csv_path)
        except Exception as exc:  # noqa: BLE001 — surface any load error to the user
            messagebox.showerror("Could not load", str(exc))
            return

        self.project_var.set(config.project_name)
        self.frame_rate_var.set(config.frame_rate)
        self.width_var.set(str(config.width))
        self.height_var.set(str(config.height))
        self.minutes_var.set(str(config.default_session_minutes))
        self._set_loaded(True)
        self.status.config(text=f"Loaded {len(rows)} row(s). Ready.")
        self._write(f"Loaded config {Path(config_path).name} and {len(rows)} CSV row(s).\n")

    def _start(self, *, dry_run: bool) -> None:
        overrides = self._collect_overrides()
        if overrides is None:
            return
        csv_path, config_path = self.csv_var.get().strip(), self.config_var.get().strip()
        recipe_out = self.recipe_var.get().strip() or "."
        self._clear()
        self._set_running(True)
        self.status.config(text="Applying…" if not dry_run else "Dry run…")
        threading.Thread(
            target=self._work,
            args=(csv_path, config_path, overrides, dry_run, recipe_out),
            daemon=True,
        ).start()

    def _collect_overrides(self) -> dict | None:
        try:
            return {
                "project_name": self.project_var.get().strip(),
                "frame_rate": self.frame_rate_var.get().strip(),
                "width": int(self.width_var.get()),
                "height": int(self.height_var.get()),
                "default_session_minutes": int(self.minutes_var.get()),
            }
        except ValueError:
            messagebox.showerror(
                "Invalid value", "Width, height and minutes must be whole numbers."
            )
            return None

    def _work(self, csv_path, config_path, overrides, dry_run, recipe_out) -> None:
        try:
            rows = read_csv(csv_path)
            config = load_config(config_path)
            if overrides["project_name"]:
                config.project_name = overrides["project_name"]
            if overrides["frame_rate"]:
                config.frame_rate = overrides["frame_rate"]
            config.width = overrides["width"]
            config.height = overrides["height"]
            config.default_session_minutes = overrides["default_session_minutes"]
            execute(rows, config, dry_run=dry_run, recipe_out=recipe_out, log=self._log)
        except Exception as exc:  # noqa: BLE001 — report to the output pane, don't crash the UI
            self._log(f"\nerror: {exc}")
        finally:
            self._queue.put(_DONE)

    # -- threading / output ---------------------------------------------- #
    def _log(self, message) -> None:
        self._queue.put(str(message))

    def _poll(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                if item is _DONE:
                    self._set_running(False)
                    self.status.config(text="Done.")
                else:
                    self._write(item + "\n")
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _write(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def _clear(self) -> None:
        self.output.delete("1.0", "end")

    def _set_loaded(self, loaded: bool) -> None:
        state = "normal" if loaded else "disabled"
        self.dry_btn.config(state=state)
        self.apply_btn.config(state=state)

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.dry_btn.config(state=state)
        self.apply_btn.config(state=state)


def main() -> int:
    root = tk.Tk()
    ConfiguratorGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
