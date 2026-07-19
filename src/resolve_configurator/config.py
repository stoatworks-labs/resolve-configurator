"""Load and validate the TOML project configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMELINE_TEMPLATE = "{start} - {presenter}"
DEFAULT_SESSION_MINUTES = 90


class ConfigError(ValueError):
    """Raised when the configuration file is malformed."""


@dataclass(frozen=True)
class AssetSpec:
    path: Path
    bin: str
    theatre: str | None  # None => global (shared) asset
    missing: bool  # true if the file does not exist on disk (warn, don't fail)


@dataclass
class Config:
    project_name: str
    create_if_missing: bool
    use_current: bool
    frame_rate: str
    width: int
    height: int
    settings: dict[str, str]  # extra passthrough Project.SetSetting() values
    default_session_minutes: int
    timeline_name_template: str
    drives: dict[str, str]
    assets: list[AssetSpec]

    def format_settings(self) -> dict[str, str]:
        """The full set of Project.SetSetting() calls: format keys + passthrough."""
        merged: dict[str, str] = {
            "timelineFrameRate": self.frame_rate,
            "timelineResolutionWidth": str(self.width),
            "timelineResolutionHeight": str(self.height),
        }
        merged.update(self.settings)
        return merged


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    try:
        with open(config_path, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc

    base_dir = config_path.resolve().parent
    return _build_config(data, base_dir)


def _build_config(data: dict, base_dir: Path) -> Config:
    project = _as_table(data, "project")
    fmt = _as_table(project, "format")
    sessions = _as_table(data, "sessions")

    frame_rate = str(fmt.get("frame_rate", "25"))
    width = _as_int(fmt, "width", 1920)
    height = _as_int(fmt, "height", 1080)

    settings = {str(k): str(v) for k, v in _as_table(project, "settings").items()}

    drives_raw = _as_table(data, "drives")
    drives = {str(k): str(v) for k, v in drives_raw.items()}

    default_minutes = _as_int(sessions, "default_session_minutes", DEFAULT_SESSION_MINUTES)
    if default_minutes <= 0:
        raise ConfigError("[sessions].default_session_minutes must be a positive integer")

    template = str(sessions.get("timeline_name_template", DEFAULT_TIMELINE_TEMPLATE))

    assets = _build_assets(data.get("assets", []), base_dir)

    return Config(
        project_name=str(project.get("name", "Resolve Session Build {date}")),
        create_if_missing=bool(project.get("create_if_missing", True)),
        use_current=bool(project.get("use_current", False)),
        frame_rate=frame_rate,
        width=width,
        height=height,
        settings=settings,
        default_session_minutes=default_minutes,
        timeline_name_template=template,
        drives=drives,
        assets=assets,
    )


def _build_assets(raw, base_dir: Path) -> list[AssetSpec]:
    if not isinstance(raw, list):
        raise ConfigError("[[assets]] must be an array of tables")
    specs: list[AssetSpec] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"[[assets]] entry #{i + 1} is not a table")
        if "path" not in entry:
            raise ConfigError(f"[[assets]] entry #{i + 1} is missing 'path'")
        rel = Path(str(entry["path"]))
        path = rel if rel.is_absolute() else (base_dir / rel)
        theatre = entry.get("theatre")
        scope = str(entry.get("scope", "global")).lower()
        # An explicit theatre implies theatre scope, regardless of any scope key.
        if theatre is None and scope != "global":
            raise ConfigError(
                f"[[assets]] entry #{i + 1}: scope '{scope}' needs a 'theatre' key"
            )
        specs.append(
            AssetSpec(
                path=path,
                bin=str(entry.get("bin", "Assets")),
                theatre=str(theatre) if theatre is not None else None,
                missing=not path.exists(),
            )
        )
    return specs


def _as_table(parent: dict, key: str) -> dict:
    value = parent.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a table")
    return value


def _as_int(parent: dict, key: str, default: int) -> int:
    value = parent.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'{key}' must be an integer, got {value!r}") from exc
