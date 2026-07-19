"""Connection to DaVinci Resolve and the backend the builder applies plans against.

External scripting requires Resolve *Studio*. This module tries, in order:
1. ``import DaVinciResolveScript`` (works inside Resolve's Console/Scripts menu,
   and externally when the environment variables are set);
2. the RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB environment variables;
3. the platform's default install paths.

If none work, :func:`connect` returns ``None`` and the caller falls back to a
dry run.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


class ResolveError(RuntimeError):
    pass


def _default_paths() -> tuple[str, str]:
    if sys.platform.startswith("darwin"):
        api = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
        lib = (
            "/Applications/DaVinci Resolve/DaVinci Resolve.app"
            "/Contents/Libraries/Fusion/fusionscript.so"
        )
    elif sys.platform.startswith("win"):
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        api = rf"{program_data}\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
        lib = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
    else:
        api = "/opt/resolve/Developer/Scripting"
        lib = "/opt/resolve/libs/Fusion/fusionscript.so"
    return os.environ.get("RESOLVE_SCRIPT_API", api), os.environ.get("RESOLVE_SCRIPT_LIB", lib)


def get_resolve():
    """Return the Resolve application object, or ``None`` if unavailable."""
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError:
        api, lib = _default_paths()
        modules = str(Path(api) / "Modules")
        if modules not in sys.path and Path(modules).is_dir():
            sys.path.append(modules)
        os.environ.setdefault("RESOLVE_SCRIPT_API", api)
        os.environ.setdefault("RESOLVE_SCRIPT_LIB", lib)
        try:
            import DaVinciResolveScript as dvr  # type: ignore
        except ImportError:
            return None
    return dvr.scriptapp("Resolve")


def connect():
    """Return a :class:`ResolveBackend`, or ``None`` if Resolve isn't reachable."""
    resolve = get_resolve()
    if resolve is None:
        return None
    return ResolveBackend(resolve)


class ResolveBackend:
    """Adapts the builder's plan operations onto the Resolve API objects."""

    def __init__(self, resolve):
        self._resolve = resolve
        self._project = None
        self._media_pool = None
        self._existing_timelines: set[str] | None = None

    # -- project ---------------------------------------------------------- #
    def select_project(self, plan) -> None:
        pm = self._resolve.GetProjectManager()
        if pm is None:
            raise ResolveError("Could not get the Resolve Project Manager.")

        if plan.use_current:
            project = pm.GetCurrentProject()
            if project is None:
                raise ResolveError("use_current is set but no project is open.")
        else:
            project = pm.LoadProject(plan.project_name)
            if project is None and plan.create_if_missing:
                project = pm.CreateProject(plan.project_name)
            if project is None:
                raise ResolveError(
                    f"Project {plan.project_name!r} not found and could not be created "
                    f"(create_if_missing={plan.create_if_missing})."
                )
        self._project = project
        self._media_pool = project.GetMediaPool()
        if self._media_pool is None:
            raise ResolveError("Could not get the Media Pool for the project.")

    def apply_settings(self, settings: dict[str, str]) -> int:
        applied = 0
        for key, value in settings.items():
            if self._project.SetSetting(key, str(value)):
                applied += 1
        return applied

    # -- media pool ------------------------------------------------------- #
    def root_folder(self):
        return self._media_pool.GetRootFolder()

    def find_or_create_folder(self, parent, name: str):
        for sub in parent.GetSubFolderList() or []:
            if sub.GetName() == name:
                return sub
        folder = self._media_pool.AddSubFolder(parent, name)
        if folder is None:
            raise ResolveError(f"Failed to create bin {name!r}.")
        return folder

    def import_media(self, folder, paths) -> None:
        self._media_pool.SetCurrentFolder(folder)
        self._media_pool.ImportMedia([str(p) for p in paths])

    def create_timeline(self, folder, name: str) -> None:
        if name in self._timeline_names():
            return  # already built on a previous run
        self._media_pool.SetCurrentFolder(folder)
        timeline = self._media_pool.CreateEmptyTimeline(name)
        if timeline is not None:
            self._timeline_names().add(name)

    def _timeline_names(self) -> set[str]:
        if self._existing_timelines is None:
            names: set[str] = set()
            count = self._project.GetTimelineCount()
            for i in range(1, count + 1):
                tl = self._project.GetTimelineByIndex(i)
                if tl is not None:
                    names.add(tl.GetName())
            self._existing_timelines = names
        return self._existing_timelines
