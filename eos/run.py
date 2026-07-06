"""Pipeline entrypoint.

Slice 2 scope: fetch -> normalize -> upcoming filter -> diff, then print
the NEW and PREVIOUSLY SEEN lists as structured JSON. No model, no
rendering, no delivery yet — those arrive in later slices.

    python -m eos.run --dry-run   # print only; do not touch state
    python -m eos.run             # print, then record items as seen
"""

import argparse
import json
import sys

from eos import normalize, state
from eos.fetchers import canvas


def _row(item):
    """Flatten an Item to a plain dict for stdout (times as UTC ISO)."""
    when = item.due_at_utc or item.starts_at_utc
    return {
        "source": item.source,
        "source_id": item.source_id,
        "kind": item.kind,
        "title": item.title,
        "when": when.isoformat() if when else None,
        "url": item.url,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="eos.run")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff but do not write state",
    )
    args = parser.parse_args(argv)

    raw = canvas.fetch_events()
    items = normalize.upcoming(normalize.normalize_events(raw))
    items.sort(key=lambda item: item.due_at_utc or item.starts_at_utc)

    conn = state.connect()
    new, seen = state.diff(conn, items)

    output = {"new": [_row(i) for i in new], "seen": [_row(i) for i in seen]}
    json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    print(f"{len(new)} new, {len(seen)} previously seen", file=sys.stderr)

    if not args.dry_run:
        state.commit_seen(conn, items)


if __name__ == "__main__":
    main()
