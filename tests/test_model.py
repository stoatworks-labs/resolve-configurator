from resolve_configurator.model import build_show


def row(date, theatre, start, name="P", email="p@e.com", n=2):
    return {
        "date": date,
        "theatre": theatre,
        "start time": start,
        "presenter name": name,
        "presenter email": email,
        "_row_number": str(n),
    }


def test_gapless_window_derivation():
    rows = [
        row("2026-08-03", "Globe", "09:30", n=2),
        row("2026-08-03", "Globe", "11:00", n=3),
    ]
    show = build_show(rows, default_session_minutes=90)
    day = show.theatres[0].days[0]
    first, last = day.windows
    # first session ends when the next one starts
    assert first.start_tc == "09:30:00:00"
    assert first.end_tc == "11:00:00:00"
    # last session of the day gets the default length (11:00 + 90m = 12:30)
    assert last.start_tc == "11:00:00:00"
    assert last.end_tc == "12:30:00:00"


def test_sessions_sorted_by_start_time():
    rows = [
        row("2026-08-03", "Globe", "11:00", n=2),
        row("2026-08-03", "Globe", "09:30", n=3),
    ]
    show = build_show(rows, default_session_minutes=90)
    starts = [w.session.start_time for w in show.theatres[0].days[0].windows]
    assert starts == ["09:30", "11:00"]


def test_exact_duplicate_dropped():
    rows = [
        row("2026-08-06", "Globe", "15:00", n=2),
        row("2026-08-06", "Globe", "15:00", n=3),
    ]
    show = build_show(rows, default_session_minutes=90)
    assert len(show.theatres[0].days[0].windows) == 1
    assert len(show.duplicates) == 1


def test_invalid_time_recorded_but_kept():
    rows = [row("2026-08-09", "Rose", "teatime", n=2)]
    show = build_show(rows, default_session_minutes=90)
    window = show.theatres[0].days[0].windows[0]
    assert window.start_tc is None
    assert window.end_tc is None
    assert len(show.invalid_time) == 1


def test_theatres_and_days_sorted():
    rows = [
        row("2026-08-05", "Swan", "13:00"),
        row("2026-08-03", "Globe", "09:30"),
        row("2026-08-04", "Globe", "10:00"),
    ]
    show = build_show(rows, default_session_minutes=90)
    assert [t.name for t in show.theatres] == ["Globe", "Swan"]
    assert [d.date for d in show.theatres[0].days] == ["2026-08-03", "2026-08-04"]


def test_window_clamped_at_midnight():
    rows = [row("2026-08-03", "Globe", "23:30", n=2)]
    show = build_show(rows, default_session_minutes=90)  # 23:30 + 90m overruns midnight
    assert show.theatres[0].days[0].windows[0].end_tc == "23:59:00:00"
