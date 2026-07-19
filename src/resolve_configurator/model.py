"""Turn canonical CSV rows into a structured show: theatre -> day -> sessions,
with a derived time window for each session.

Grouping/dedup mirrors nc-filedropbatch: sessions are keyed on
(Theatre, Date, Start Time), the same key its Google-Sheet sync matches on, so
exact-duplicate rows collapse to one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Session:
    date: str  # raw "YYYY-MM-DD"
    theatre: str  # raw theatre label (may be empty)
    start_time: str  # raw "HH:MM"
    presenter_name: str
    presenter_email: str
    row_number: int
    start_minutes: int | None  # minutes past midnight, or None if unparseable
    date_valid: bool

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.theatre, self.date, self.start_time)


@dataclass(frozen=True)
class SessionWindow:
    session: Session
    end_minutes: int | None  # None when the start time couldn't be parsed

    @property
    def start_tc(self) -> str | None:
        return _minutes_to_tc(self.session.start_minutes)

    @property
    def end_tc(self) -> str | None:
        return _minutes_to_tc(self.end_minutes)


@dataclass
class Day:
    date: str
    windows: list[SessionWindow] = field(default_factory=list)


@dataclass
class Theatre:
    name: str  # raw label
    days: list[Day] = field(default_factory=list)


@dataclass(frozen=True)
class PlannedSession:
    """A session after the builder has assigned it a final timeline name and bin path."""

    theatre: str  # raw theatre label
    date: str
    window: SessionWindow
    timeline_name: str
    bin_path: tuple[str, ...]  # sanitized bin names, e.g. ("Globe", "2026-08-03")


@dataclass
class Show:
    theatres: list[Theatre] = field(default_factory=list)
    duplicates: list[Session] = field(default_factory=list)
    invalid_time: list[Session] = field(default_factory=list)

    def iter_windows(self):
        for theatre in self.theatres:
            for day in theatre.days:
                for window in day.windows:
                    yield theatre, day, window


def build_show(rows: list[dict[str, str]], default_session_minutes: int) -> Show:
    """Build a :class:`Show` from canonical CSV rows."""
    sessions, duplicates = _rows_to_sessions(rows)

    grouped: dict[str, dict[str, list[Session]]] = {}
    for session in sessions:
        grouped.setdefault(session.theatre, {}).setdefault(session.date, []).append(session)

    show = Show(duplicates=duplicates)
    for theatre_name in sorted(grouped):
        theatre = Theatre(name=theatre_name)
        for date in sorted(grouped[theatre_name]):
            day_sessions = grouped[theatre_name][date]
            day = Day(date=date)
            day.windows = _derive_windows(day_sessions, default_session_minutes, show)
            theatre.days.append(day)
        show.theatres.append(theatre)
    return show


def _rows_to_sessions(rows: list[dict[str, str]]) -> tuple[list[Session], list[Session]]:
    seen: set[tuple[str, str, str]] = set()
    kept: list[Session] = []
    duplicates: list[Session] = []
    for row in rows:
        session = _row_to_session(row)
        if session.key in seen:
            duplicates.append(session)
            continue
        seen.add(session.key)
        kept.append(session)
    return kept, duplicates


def _row_to_session(row: dict[str, str]) -> Session:
    start_minutes = _parse_time(row.get("start time", ""))
    return Session(
        date=row.get("date", ""),
        theatre=row.get("theatre", ""),
        start_time=row.get("start time", ""),
        presenter_name=row.get("presenter name", ""),
        presenter_email=row.get("presenter email", ""),
        row_number=int(row.get("_row_number", "0") or "0"),
        start_minutes=start_minutes,
        date_valid=_is_valid_date(row.get("date", "")),
    )


def _derive_windows(
    sessions: list[Session], default_minutes: int, show: Show
) -> list[SessionWindow]:
    # Sessions with an unparseable start time have no place in the timeline;
    # keep them (a timeline is still made) but give them no window and record them.
    timed = sorted(
        (s for s in sessions if s.start_minutes is not None),
        key=lambda s: (s.start_minutes, s.row_number),
    )
    untimed = [s for s in sessions if s.start_minutes is None]
    show.invalid_time.extend(untimed)

    windows: list[SessionWindow] = []
    for i, session in enumerate(timed):
        if i + 1 < len(timed):
            end = timed[i + 1].start_minutes
        else:
            end = session.start_minutes + default_minutes
        windows.append(SessionWindow(session=session, end_minutes=end))
    windows.extend(SessionWindow(session=s, end_minutes=None) for s in untimed)
    return windows


def _parse_time(value: str) -> int | None:
    value = value.strip()
    if ":" not in value:
        return None
    hh, _, mm = value.partition(":")
    if not (hh.isdigit() and mm.isdigit()):
        return None
    hours, minutes = int(hh), int(mm)
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


def _is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _minutes_to_tc(minutes: int | None) -> str | None:
    """Time-of-day timecode 'HH:MM:00:00'. Clamped to 23:59 if it overruns midnight."""
    if minutes is None:
        return None
    minutes = min(minutes, 23 * 60 + 59)
    return f"{minutes // 60:02d}:{minutes % 60:02d}:00:00"
