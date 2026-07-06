"""Slice 1: Canvas ICS fetcher.

Fetch the Canvas calendar feed at CANVAS_ICS_URL, parse it with icalendar,
and print each upcoming assignment/event to stdout as structured JSON:
title, course (if available), due/start time, and url.

Deliberately minimal per the build order: no retries, no classes, no
normalization. Those arrive in later slices.

    python -m eos.fetchers.canvas
"""

import json
import os
import re
import sys
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv
from icalendar import Calendar


def _to_utc(dt):
    """Normalize an icalendar DTSTART value to an aware UTC datetime.

    icalendar hands back either a `datetime` (aware or naive) or, for
    all-day entries, a `date`. Canvas feeds are usually UTC ("Z"), so a
    naive datetime is assumed UTC. All-day dates become midnight UTC.
    Used for the "is this upcoming?" check and for stable display.
    """
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)


def _split_course(summary):
    """Canvas encodes the course as a trailing "[Course Name]" in SUMMARY."""
    match = re.search(r"\[([^\]]+)\]\s*$", summary)
    if match:
        return summary[: match.start()].strip(), match.group(1).strip()
    return summary.strip(), None


def main():
    load_dotenv()
    url = os.environ.get("CANVAS_ICS_URL")
    if not url:
        sys.exit("CANVAS_ICS_URL is not set in .env")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        # The feed URL embeds a secret token; requests puts the full URL in
        # its exception text, so report only the status, never the URL.
        status = exc.response.status_code if exc.response is not None else "no response"
        sys.exit(f"Failed to fetch Canvas ICS feed ({status})")

    calendar = Calendar.from_ical(response.content)
    now = datetime.now(timezone.utc)

    items = []
    for event in calendar.walk("VEVENT"):
        dtstart = event.get("DTSTART")
        if dtstart is None:
            continue
        when = _to_utc(dtstart.dt)
        if when < now:
            continue  # past — only upcoming items belong in the briefing

        title, course = _split_course(str(event.get("SUMMARY", "")).strip())
        url_prop = event.get("URL")
        items.append(
            {
                "title": title,
                "course": course,
                "when": when.isoformat(),
                "url": str(url_prop) if url_prop else None,
            }
        )

    items.sort(key=lambda item: item["when"])
    json.dump(items, sys.stdout, indent=2)
    sys.stdout.write("\n")
    print(f"{len(items)} upcoming item(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
