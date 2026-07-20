"""Desktop editor for the Resolve Configurator.

A Tkinter window laid out like the sibling nc-filedropbatch page — a titled
header, a manual sessions table you edit row by row, project settings, and
per-theatre asset browsing — styled in DaVinci Resolve's grey-on-grey palette.
All the real work still goes through ``core.execute``; this module only gathers
form state and hands it over via ``formmodel``.

Launch with ``resolve-configure-gui`` or ``python -m resolve_configurator.gui``.
"""

from __future__ import annotations

import csv
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import formmodel
from .config import load_config
from .core import execute
from .csv_reader import read_csv

_DONE = object()
BINS = ["Backgrounds", "PiP", "Slides"]
GLOBAL = "__global__"

# DaVinci Resolve-ish grey palette.
BG = "#1e1e1e"
PANEL = "#2a2a2a"
FIELD = "#3a3a3a"
FIELD_TXT = "#d6d6d6"
TEXT = "#c8c8c8"
MUTED = "#8a8a8a"
BTN = "#3c3c3c"
BTN_ACTIVE = "#4a4a4a"
BORDER = "#454545"
ACCENT = "#5b7fa6"
ACCENT_ACTIVE = "#6b8fb6"
HEADER_BG = "#242424"


class ConfiguratorGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Resolve Configurator")
        root.minsize(820, 720)
        root.configure(bg=BG)
        self._apply_theme()

        # form vars
        self.project_var = tk.StringVar(value="MyEvent {date}")
        self.frame_rate_var = tk.StringVar(value="25")
        self.width_var = tk.StringVar(value="1920")
        self.height_var = tk.StringVar(value="1080")
        self.minutes_var = tk.StringVar(value="90")
        self.recipe_var = tk.StringVar(value=".")

        # persistent asset/session state (survives panel rebuilds)
        self._session_rows: list[dict[str, tk.StringVar]] = []
        self.drive_vars: dict[str, tk.StringVar] = {}
        self.asset_data: dict[tuple[str, str], list[str]] = {}
        self.listboxes: dict[tuple[str, str], tk.Listbox] = {}
        self.rendered_theatres: list[str] = []
        self._queue: queue.Queue = queue.Queue()

        outer = ttk.Frame(root, padding=0)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(5, weight=1)

        self._build_header(outer, 0)
        self._build_sessions(outer, 1)
        self._build_settings(outer, 2)
        self._build_assets(outer, 3)
        self._build_actions(outer, 4)
        self._build_output(outer, 5)

        self._render_asset_panels([])
        self.root.after(80, self._poll)

    # -- theme ------------------------------------------------------------ #
    def _apply_theme(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=PANEL, foreground=TEXT, bordercolor=BORDER,
                        fieldbackground=FIELD, focuscolor=PANEL)
        style.configure("TFrame", background=PANEL)
        style.configure("Header.TFrame", background=HEADER_BG)
        style.configure("TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("HeaderTitle.TLabel", background=HEADER_BG, foreground="#ececec",
                        font=("TkDefaultFont", 15, "bold"))
        style.configure("HeaderSub.TLabel", background=HEADER_BG, foreground=MUTED)
        style.configure("TLabelframe", background=PANEL, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=PANEL, foreground=MUTED)
        style.configure("TButton", background=BTN, foreground=TEXT, bordercolor=BORDER, padding=5)
        style.map("TButton", background=[("active", BTN_ACTIVE)],
                  foreground=[("disabled", MUTED)])
        style.configure("Primary.TButton", background=ACCENT, foreground="#ffffff")
        style.map("Primary.TButton", background=[("active", ACCENT_ACTIVE)])
        style.configure("TEntry", fieldbackground=FIELD, foreground=FIELD_TXT,
                        insertcolor=FIELD_TXT, bordercolor=BORDER)
        style.configure("Vertical.TScrollbar", background=BTN, troughcolor=BG, bordercolor=BORDER,
                        arrowcolor=TEXT)

    # -- header ----------------------------------------------------------- #
    def _build_header(self, parent, row) -> None:
        bar = ttk.Frame(parent, style="Header.TFrame", padding=(16, 12))
        bar.grid(row=row, column=0, sticky="ew")
        swatch = tk.Frame(bar, bg=ACCENT, width=14, height=14)
        swatch.pack(side="left", padx=(0, 10))
        swatch.pack_propagate(False)
        box = ttk.Frame(bar, style="Header.TFrame")
        box.pack(side="left")
        ttk.Label(box, text="Resolve Configurator", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(box, text="Build a DaVinci Resolve project from a theatre / session show.",
                  style="HeaderSub.TLabel").pack(anchor="w")

    # -- sessions --------------------------------------------------------- #
    def _build_sessions(self, parent, row) -> None:
        frame = ttk.LabelFrame(parent, text="Sessions", padding=8)
        frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(10, 4))
        frame.columnconfigure(0, weight=1)

        bar = ttk.Frame(frame)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(bar, text="Load CSV…", command=self._load_csv).pack(side="left")
        ttk.Button(bar, text="Add row",
                   command=lambda: self._add_session_row()).pack(side="left", padx=6)
        ttk.Button(bar, text="Clear", command=self._clear_sessions).pack(side="left")
        ttk.Button(bar, text="Export CSV…", command=self._export_csv).pack(side="left", padx=6)

        # column headers, widths shared with each row
        self._cols = [("Date", 12), ("Theatre", 16), ("Start time", 9),
                      ("Presenter name", 20), ("Presenter email", 24)]
        head = ttk.Frame(frame)
        head.grid(row=1, column=0, sticky="w")
        for label, width in self._cols:
            ttk.Label(head, text=label, width=width).pack(side="left", padx=2)
        ttk.Label(head, text="", width=3).pack(side="left")

        self._sessions_scroll = _ScrollArea(frame, height=118)
        self._sessions_scroll.grid(row=2, column=0, sticky="ew")

    def _add_session_row(self, values: dict | None = None) -> None:
        values = values or {}
        rowf = ttk.Frame(self._sessions_scroll.body)
        rowf.pack(fill="x", pady=1)
        vars_: dict[str, tk.StringVar] = {}
        for key, (_, width) in zip(formmodel.SESSION_KEYS, self._cols, strict=True):
            var = tk.StringVar(value=str(values.get(key, "")))
            ttk.Entry(rowf, textvariable=var, width=width).pack(side="left", padx=2)
            vars_[key] = var
        entry = {"frame": rowf, "vars": vars_}
        ttk.Button(rowf, text="✕", width=3,
                   command=lambda e=entry: self._delete_session_row(e)).pack(side="left")
        self._session_rows.append(entry)

    def _delete_session_row(self, entry) -> None:
        entry["frame"].destroy()
        self._session_rows.remove(entry)

    def _clear_sessions(self) -> None:
        for entry in list(self._session_rows):
            self._delete_session_row(entry)

    def _collect_sessions(self) -> list[dict]:
        return [{k: v.get() for k, v in e["vars"].items()} for e in self._session_rows]

    def _load_csv(self) -> None:
        path = filedialog.askopenfilename(title="Sessions CSV",
                                          filetypes=[("CSV", "*.csv"), ("All files", "*")])
        if not path:
            return
        try:
            rows = read_csv(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read CSV", str(exc))
            return
        self._clear_sessions()
        for r in rows:
            self._add_session_row(r)
        if self.recipe_var.get() in ("", "."):
            self.recipe_var.set(str(Path(path).parent))
        self._sync_theatres()
        self.status.config(text=f"Loaded {len(rows)} session row(s).")

    def _export_csv(self) -> None:
        rows = formmodel.rows_from_sessions(self._collect_sessions())
        if not rows:
            messagebox.showinfo("Nothing to export", "Add some session rows first.")
            return
        path = filedialog.asksaveasfilename(title="Export sessions CSV", defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        header = ["Date", "Theatre", "Start Time", "presenter name", "presenter email"]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            for r in rows:
                writer.writerow([r[k] for k in formmodel.SESSION_KEYS])
        self.status.config(text=f"Exported {len(rows)} row(s).")

    # -- settings --------------------------------------------------------- #
    def _build_settings(self, parent, row) -> None:
        frame = ttk.LabelFrame(parent, text="Project settings", padding=8)
        frame.grid(row=row, column=0, sticky="ew", padx=10, pady=4)
        for c in (1, 3):
            frame.columnconfigure(c, weight=1)

        self._labeled(frame, 0, 0, "Project name", self.project_var, span=3)
        self._labeled(frame, 1, 0, "Frame rate", self.frame_rate_var)
        self._labeled(frame, 1, 2, "Default session mins", self.minutes_var)
        self._labeled(frame, 2, 0, "Width", self.width_var)
        self._labeled(frame, 2, 2, "Height", self.height_var)

        ttk.Label(frame, text="Recipe output dir").grid(row=3, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame, textvariable=self.recipe_var).grid(row=3, column=1, columnspan=2,
                                                            sticky="ew", padx=6, pady=3)
        ttk.Button(frame, text="Browse…", command=self._pick_recipe).grid(row=3, column=3, padx=6)

        tools = ttk.Frame(frame)
        tools.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(tools, text="Load config…", command=self._load_config).pack(side="left")
        ttk.Button(tools, text="Save config…", command=self._save_config).pack(side="left", padx=6)

    def _labeled(self, parent, row, col, label, var, span=1) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=6, pady=3)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=col + 1, columnspan=span,
                                                 sticky="ew", padx=6, pady=3)

    def _pick_recipe(self) -> None:
        path = filedialog.askdirectory(title="Recipe output directory")
        if path:
            self.recipe_var.set(path)

    # -- assets ----------------------------------------------------------- #
    def _build_assets(self, parent, row) -> None:
        frame = ttk.LabelFrame(parent, text="Assets (backgrounds / PiP / slides)", padding=8)
        frame.grid(row=row, column=0, sticky="ew", padx=10, pady=4)
        frame.columnconfigure(0, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Button(bar, text="Sync theatres from sessions",
                   command=self._sync_theatres).pack(side="left")
        ttk.Label(bar, text="  add images per theatre below",
                  style="Muted.TLabel").pack(side="left")
        self._assets_scroll = _ScrollArea(frame, height=150)
        self._assets_scroll.grid(row=1, column=0, sticky="ew")

    def _sync_theatres(self) -> None:
        rows = formmodel.rows_from_sessions(self._collect_sessions())
        theatres = formmodel.distinct_theatres(rows)
        # keep any theatre that already has a drive or assets, even if not in the table
        extra = {s for (s, _b), lst in self.asset_data.items() if s != GLOBAL and lst}
        extra |= {t for t, v in self.drive_vars.items() if v.get().strip()}
        for t in extra:
            if t not in theatres:
                theatres.append(t)
        self._render_asset_panels(theatres)

    def _render_asset_panels(self, theatres: list[str]) -> None:
        self.rendered_theatres = theatres
        self.listboxes = {}
        for child in self._assets_scroll.body.winfo_children():
            child.destroy()

        scopes = [(GLOBAL, "Global (all theatres)", None)]
        scopes += [(t, t, t) for t in theatres]
        for scope_key, label, theatre in scopes:
            panel = ttk.LabelFrame(self._assets_scroll.body, text=label, padding=6)
            panel.pack(fill="x", pady=4, padx=2)
            panel.columnconfigure(1, weight=1)
            r = 0
            if theatre is not None:
                var = self.drive_vars.setdefault(theatre, tk.StringVar())
                ttk.Label(panel, text="Record drive").grid(
                    row=r, column=0, sticky="w", padx=4, pady=2)
                ttk.Entry(panel, textvariable=var).grid(row=r, column=1, columnspan=2,
                                                        sticky="ew", padx=4, pady=2)
                r += 1
            for binname in BINS:
                key = (scope_key, binname)
                self.asset_data.setdefault(key, [])
                ttk.Label(panel, text=binname).grid(row=r, column=0, sticky="nw", padx=4, pady=2)
                lb = tk.Listbox(
                    panel, height=2, bg=FIELD, fg=FIELD_TXT, borderwidth=0,
                    highlightthickness=1, highlightbackground=BORDER, selectbackground=ACCENT,
                    selectforeground="#ffffff", exportselection=False)
                lb.grid(row=r, column=1, sticky="ew", padx=4, pady=2)
                for p in self.asset_data[key]:
                    lb.insert("end", Path(p).name)
                self.listboxes[key] = lb
                btns = ttk.Frame(panel)
                btns.grid(row=r, column=2, sticky="w", padx=4)
                ttk.Button(btns, text="Add images…", width=12,
                           command=lambda k=key: self._add_images(k)).pack(anchor="w", pady=1)
                ttk.Button(btns, text="Remove", width=12,
                           command=lambda k=key: self._remove_images(k)).pack(anchor="w", pady=1)
                r += 1
        self._assets_scroll.refresh()

    def _add_images(self, key) -> None:
        paths = filedialog.askopenfilenames(
            title="Add image(s)",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.tif *.tiff *.exr *.mov *.mp4"),
                ("All files", "*"),
            ],
        )
        if not paths:
            return
        for p in paths:
            self.asset_data[key].append(p)
            self.listboxes[key].insert("end", Path(p).name)

    def _remove_images(self, key) -> None:
        lb = self.listboxes[key]
        for idx in sorted(lb.curselection(), reverse=True):
            del self.asset_data[key][idx]
            lb.delete(idx)

    def _collect_assets(self) -> list[dict]:
        assets: list[dict] = []
        for scope_key in [GLOBAL, *self.rendered_theatres]:
            theatre = None if scope_key == GLOBAL else scope_key
            for binname in BINS:
                for path in self.asset_data.get((scope_key, binname), []):
                    assets.append({"path": path, "bin": binname, "theatre": theatre})
        return assets

    def _collect_drives(self) -> dict[str, str]:
        return {t: self.drive_vars[t].get().strip()
                for t in self.rendered_theatres if t in self.drive_vars}

    # -- actions ---------------------------------------------------------- #
    def _build_actions(self, parent, row) -> None:
        bar = ttk.Frame(parent, padding=(10, 6))
        bar.grid(row=row, column=0, sticky="ew")
        self.dry_btn = ttk.Button(bar, text="Dry run", command=lambda: self._start(dry_run=True))
        self.apply_btn = ttk.Button(bar, text="Apply to Resolve", style="Primary.TButton",
                                    command=lambda: self._start(dry_run=False))
        self.dry_btn.pack(side="left")
        self.apply_btn.pack(side="left", padx=6)
        self.status = ttk.Label(bar, text="Add or load sessions to begin.", style="Muted.TLabel")
        self.status.pack(side="right")

    def _build_output(self, parent, row) -> None:
        frame = ttk.Frame(parent, padding=(10, 0, 10, 10))
        frame.grid(row=row, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.output = scrolledtext.ScrolledText(
            frame, height=9, wrap="none", font=("Menlo", 11),
            bg="#181818", fg=TEXT, insertbackground=TEXT, borderwidth=0, highlightthickness=0)
        self.output.grid(row=0, column=0, sticky="nsew")

    # -- config load/save ------------------------------------------------- #
    def _gather(self) -> dict | None:
        try:
            width = int(self.width_var.get())
            height = int(self.height_var.get())
            minutes = int(self.minutes_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid value", "Width, height and minutes must be whole numbers.")
            return None
        self._sync_theatres()
        return {
            "sessions": self._collect_sessions(),
            "project_name": self.project_var.get().strip(),
            "frame_rate": self.frame_rate_var.get().strip(),
            "width": width, "height": height, "default_session_minutes": minutes,
            "drives": self._collect_drives(),
            "assets": self._collect_assets(),
        }

    def _save_config(self) -> None:
        form = self._gather()
        if form is None:
            return
        config = formmodel.build_config(**{k: v for k, v in form.items() if k != "sessions"})
        path = filedialog.asksaveasfilename(title="Save project config", defaultextension=".toml",
                                            filetypes=[("TOML", "*.toml")])
        if not path:
            return
        Path(path).write_text(formmodel.config_to_toml(config), encoding="utf-8")
        self.status.config(text=f"Saved config to {Path(path).name}.")

    def _load_config(self) -> None:
        path = filedialog.askopenfilename(title="Load project config",
                                          filetypes=[("TOML", "*.toml"), ("All files", "*")])
        if not path:
            return
        try:
            config = load_config(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not load config", str(exc))
            return
        self.project_var.set(config.project_name)
        self.frame_rate_var.set(config.frame_rate)
        self.width_var.set(str(config.width))
        self.height_var.set(str(config.height))
        self.minutes_var.set(str(config.default_session_minutes))
        for theatre, drive in config.drives.items():
            self.drive_vars.setdefault(theatre, tk.StringVar()).set(drive)
        for spec in config.assets:
            key = (spec.theatre or GLOBAL, spec.bin if spec.bin in BINS else "Backgrounds")
            self.asset_data.setdefault(key, []).append(str(spec.path))
        self._sync_theatres()
        self.status.config(text=f"Loaded config {Path(path).name}.")

    # -- run -------------------------------------------------------------- #
    def _start(self, *, dry_run: bool) -> None:
        form = self._gather()
        if form is None:
            return
        recipe_out = self.recipe_var.get().strip() or "."
        self.output.delete("1.0", "end")
        self._set_running(True)
        self.status.config(text="Applying…" if not dry_run else "Dry run…")
        threading.Thread(target=self._work, args=(form, recipe_out, dry_run), daemon=True).start()

    def _work(self, form, recipe_out, dry_run) -> None:
        try:
            rows = formmodel.rows_from_sessions(form["sessions"])
            if not rows:
                self._log("No session rows to build. Add or load some sessions first.")
                return
            config = formmodel.build_config(**{k: v for k, v in form.items() if k != "sessions"})
            execute(rows, config, dry_run=dry_run, recipe_out=recipe_out, log=self._log)
        except Exception as exc:  # noqa: BLE001
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
                    self.output.insert("end", item + "\n")
                    self.output.see("end")
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.dry_btn.config(state=state)
        self.apply_btn.config(state=state)


class _ScrollArea(ttk.Frame):
    """A fixed-height, vertically scrollable container; add widgets to ``.body``."""

    def __init__(self, parent, height: int) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, height=height, bg=PANEL, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_body_configure(self, _event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)

    def refresh(self) -> None:
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


def main() -> int:
    root = tk.Tk()
    ConfiguratorGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
