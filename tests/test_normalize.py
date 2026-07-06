"""normalize: raw ICS events -> Items. No network, fixture-driven."""

from datetime import datetime, timezone
from pathlib import Path

from eos.fetchers import canvas
from eos.normalize import Item, normalize_events, upcoming

FIXTURE = Path(__file__).parent / "fixtures" / "canvas_sample.ics"


def _items():
    raw = canvas.parse_events(FIXTURE.read_bytes())
    return normalize_events(raw)


def test_parse_events_reads_all_vevents():
    raw = canvas.parse_events(FIXTURE.read_bytes())
    assert len(raw) == 3
    # fetcher does no transformation: course tag still on the summary
    assert any(r["summary"] == "Problem Set 5 [PHYS 221]" for r in raw)


def test_course_is_folded_into_title():
    ps5 = next(i for i in _items() if i.source_id.endswith("assignment-2@canvas.case.edu"))
    assert ps5.title == "PHYS 221: Problem Set 5"


def test_assignment_classification_and_due_time():
    ps5 = next(i for i in _items() if "Problem Set 5" in i.title)
    assert ps5.kind == "assignment"
    assert ps5.due_at_utc == datetime(2099, 12, 1, 23, 59, tzinfo=timezone.utc)
    assert ps5.starts_at_utc is None


def test_all_day_event_classification_and_utc_midnight():
    reading = next(i for i in _items() if i.title == "Reading Day")
    assert reading.kind == "event"
    assert reading.starts_at_utc == datetime(2099, 12, 15, 0, 0, tzinfo=timezone.utc)
    assert reading.due_at_utc is None


def test_times_are_timezone_aware():
    for item in _items():
        when = item.due_at_utc or item.starts_at_utc
        assert when.tzinfo is not None


def test_upcoming_filters_out_past_items():
    kept = upcoming(_items())  # 2020 assignment is well in the past
    titles = {i.title for i in kept}
    assert "MATH 101: Old Homework" not in titles
    assert len(kept) == 2


def test_upcoming_respects_injected_now():
    # with a now after every fixture date, nothing survives
    future = datetime(2100, 1, 1, tzinfo=timezone.utc)
    assert upcoming(_items(), now=future) == []
