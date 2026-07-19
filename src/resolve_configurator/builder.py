"""Build a media-pool plan from a show, render it, and apply it to Resolve.

The plan is pure data (``Plan``), computed with no Resolve dependency, so it can
be printed in a dry run and asserted on in tests. ``apply_plan`` walks the same
plan against a backend that actually talks to Resolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .model import PlannedSession, Show
from .naming import sanitize_segment

ASSETS_BIN = "Assets"


@dataclass
class FolderNode:
    name: str
    children: list[FolderNode] = field(default_factory=list)
    timelines: list[str] = field(default_factory=list)
    media: list[Path] = field(default_factory=list)

    def child(self, name: str) -> FolderNode:
        """Find-or-create a child bin by name."""
        for c in self.children:
            if c.name == name:
                return c
        node = FolderNode(name=name)
        self.children.append(node)
        return node


@dataclass
class Plan:
    project_name: str
    create_if_missing: bool
    use_current: bool
    settings: dict[str, str]
    root_children: list[FolderNode]
    planned_sessions: list[PlannedSession]
    warnings: list[str] = field(default_factory=list)


def build_plan(show: Show, config: Config) -> Plan:
    warnings: list[str] = []
    project_name = _expand_name(config.project_name, show)

    root: list[FolderNode] = []
    assets_root = _build_assets(config, root, warnings)

    used_names: set[str] = set()
    planned: list[PlannedSession] = []

    for theatre in show.theatres:
        theatre_bin = sanitize_segment(theatre.name)
        theatre_node = _get_top(root, theatre_bin)
        # theatre-scoped assets live under <Theatre>/Assets/<bin>
        for spec in config.assets:
            if spec.theatre == theatre.name:
                sub = theatre_node.child(ASSETS_BIN).child(sanitize_segment(spec.bin))
                sub.media.append(spec.path)

        for day in theatre.days:
            date_bin = sanitize_segment(day.date)
            day_node = theatre_node.child(date_bin)
            for window in day.windows:
                name = _timeline_name(
                    config.timeline_name_template, theatre, day, window, used_names
                )
                day_node.timelines.append(name)
                planned.append(
                    PlannedSession(
                        theatre=theatre.name,
                        date=day.date,
                        window=window,
                        timeline_name=name,
                        bin_path=(theatre_bin, date_bin),
                    )
                )

    # Assets bin first in the pool, then theatres.
    ordered = ([assets_root] if assets_root else []) + [n for n in root if n is not assets_root]
    return Plan(
        project_name=project_name,
        create_if_missing=config.create_if_missing,
        use_current=config.use_current,
        settings=config.format_settings(),
        root_children=ordered,
        planned_sessions=planned,
        warnings=warnings,
    )


def _build_assets(config: Config, root: list[FolderNode], warnings: list[str]) -> FolderNode | None:
    global_specs = [s for s in config.assets if s.theatre is None]
    for spec in config.assets:
        if spec.missing:
            warnings.append(f"Asset file not found (import will be skipped): {spec.path}")
    if not global_specs:
        return None
    assets_root = FolderNode(name=ASSETS_BIN)
    for spec in global_specs:
        assets_root.child(sanitize_segment(spec.bin)).media.append(spec.path)
    root.append(assets_root)
    return assets_root


def _get_top(root: list[FolderNode], name: str) -> FolderNode:
    for node in root:
        if node.name == name:
            return node
    node = FolderNode(name=name)
    root.append(node)
    return node


def _timeline_name(template, theatre, day, window, used: set[str]) -> str:
    session = window.session
    base = template.format(
        start=session.start_time or "no-time",
        presenter=session.presenter_name or "no-presenter",
        theatre=theatre.name,
        date=day.date,
    )
    name = sanitize_segment(base)
    if name in used:
        name = sanitize_segment(f"{base} [{theatre.name} {day.date}]")
    counter = 2
    unique = name
    while unique in used:
        unique = sanitize_segment(f"{name} ({counter})")
        counter += 1
    used.add(unique)
    return unique


def _expand_name(template: str, show: Show) -> str:
    dates = [
        day.date
        for theatre in show.theatres
        for day in theatre.days
        if day.windows
    ]
    earliest = min(dates) if dates else ""
    return template.replace("{date}", earliest)


# --------------------------------------------------------------------------- #
# Rendering (dry run)
# --------------------------------------------------------------------------- #

def render_plan(plan: Plan) -> str:
    lines = [
        f"Project: {plan.project_name}"
        + ("  [use current]" if plan.use_current else "")
        + ("" if plan.use_current else f"  [create_if_missing={plan.create_if_missing}]"),
        "Settings:",
    ]
    for key, value in plan.settings.items():
        lines.append(f"    {key} = {value}")
    lines.append("Media pool:")
    for node in plan.root_children:
        _render_node(node, 1, lines)
    if plan.warnings:
        lines.append("Warnings:")
        for w in plan.warnings:
            lines.append(f"    ! {w}")
    return "\n".join(lines) + "\n"


def _render_node(node: FolderNode, depth: int, lines: list[str]) -> None:
    indent = "    " * depth
    lines.append(f"{indent}📁 {node.name}")
    for path in node.media:
        lines.append(f"{indent}    • {path.name}")
    for tl in node.timelines:
        lines.append(f"{indent}    ▸ {tl}")
    for child in node.children:
        _render_node(child, depth + 1, lines)


# --------------------------------------------------------------------------- #
# Apply (live)
# --------------------------------------------------------------------------- #

def apply_plan(plan: Plan, backend, log=print) -> None:
    """Execute *plan* against a Resolve backend (see resolve_api.ResolveBackend)."""
    backend.select_project(plan)
    applied = backend.apply_settings(plan.settings)
    log(f"Applied {applied} project setting(s).")

    root_handle = backend.root_folder()
    for node in plan.root_children:
        _apply_node(node, root_handle, backend, log)
    log(f"Built {len(plan.planned_sessions)} timeline(s).")


def _apply_node(node: FolderNode, parent_handle, backend, log) -> None:
    handle = backend.find_or_create_folder(parent_handle, node.name)
    if node.media:
        existing = [p for p in node.media if p.exists()]
        if existing:
            backend.import_media(handle, existing)
    for tl in node.timelines:
        backend.create_timeline(handle, tl)
    for child in node.children:
        _apply_node(child, handle, backend, log)
