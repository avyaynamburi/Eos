"""Canvas ICS fetcher — raw source data only, no transformation.

Per the fetcher contract in CLAUDE.md, this module only does I/O and
parsing: fetch the ICS feed at CANVAS_ICS_URL and hand back raw event
dicts. All semantic work (upcoming filter, course split, UTC conversion,
mapping to the Item dataclass) lives in normalize.py.
"""

import os
import sys

import requests
from dotenv import load_dotenv
from icalendar import Calendar


def parse_events(ics_bytes):
    """Parse ICS bytes into raw event dicts. Pure: no network, no filtering.

    Values are handed back as icalendar decoded them — notably `dtstart`
    is a `datetime` or (for all-day entries) a `date`, and `summary` still
    carries any trailing "[Course]". normalize.py interprets all of this.
    """
    calendar = Calendar.from_ical(ics_bytes)
    events = []
    for component in calendar.walk("VEVENT"):
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        uid = component.get("UID")
        url = component.get("URL")
        events.append(
            {
                "uid": str(uid) if uid is not None else None,
                "summary": str(component.get("SUMMARY", "")),
                "dtstart": dtstart.dt if dtstart is not None else None,
                "dtend": dtend.dt if dtend is not None else None,
                "url": str(url) if url else None,
            }
        )
    return events


def fetch_events():
    """Fetch and parse the configured Canvas ICS feed. Raw dicts, no transform."""
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

    return parse_events(response.content)
