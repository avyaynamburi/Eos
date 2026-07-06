"""Raw source events -> the Item dataclass.

This is where the deterministic transformation moved out of the fetchers
lives: course-splitting, UTC conversion, kind classification, and the
upcoming/past filter. Code does logic; the model never touches any of this.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass
class Item:
    """One normalized thing worth briefing. Times are aware UTC or None.

    The contract consumed downstream (state, summarize, render). `course`
    is intentionally not a field here — it is folded into `title` (see
    normalize_events) to keep this contract stable.
    """

    source: str
    source_id: str
    kind: str  # "assignment" | "event"
    title: str
    due_at_utc: datetime | None
    starts_at_utc: datetime | None
    url: str | None
    snippet: str | None


def _to_utc(value):
    """Normalize an icalendar dt value to an aware UTC datetime.

    icalendar yields either a `datetime` (aware or naive) or, for all-day
    entries, a `date`. Canvas feeds are UTC ("Z"), so a naive datetime is
    assumed UTC; an all-day date becomes midnight UTC.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


_COURSE_RE = re.compile(r"\[([^\]]+)\]\s*$")


def _split_course(summary):
    """Canvas encodes the course as a trailing "[Course Name]" in SUMMARY."""
    match = _COURSE_RE.search(summary)
    if match:
        return summary[: match.start()].strip(), match.group(1).strip()
    return summary.strip(), None


def _is_assignment(raw):
    """Canvas assignment feed entries carry /assignments/ URLs and 'assignment'
    UIDs; calendar/course events do not."""
    url = raw.get("url") or ""
    uid = raw.get("uid") or ""
    return "/assignments/" in url or "assignment" in uid.lower()


def normalize_events(raw_events):
    """Map raw Canvas event dicts to Items. No filtering happens here."""
    items = []
    for raw in raw_events:
        dtstart = raw.get("dtstart")
        if dtstart is None:
            continue  # nothing to place on a timeline
        when = _to_utc(dtstart)

        title, course = _split_course(str(raw.get("summary", "")).strip())
        if course:
            # Item has no course field, so keep the context in the title.
            title = f"{course}: {title}"

        assignment = _is_assignment(raw)
        source_id = str(
            raw.get("uid") or raw.get("url") or f"{title}|{when.isoformat()}"
        )
        items.append(
            Item(
                source="canvas",
                source_id=source_id,
                kind="assignment" if assignment else "event",
                title=title,
                due_at_utc=when if assignment else None,
                starts_at_utc=None if assignment else when,
                url=raw.get("url"),
                snippet=None,  # ICS has no snippet; Gmail supplies these later
            )
        )
    return items


def upcoming(items, now=None):
    """Keep only items whose due/start time is now or later."""
    now = now or datetime.now(timezone.utc)
    result = []
    for item in items:
        when = item.due_at_utc or item.starts_at_utc
        if when is not None and when >= now:
            result.append(item)
    return result
