"""SQLite state: what have we already seen?

Tracks (source, source_id, content_hash, first_seen_at). The diff is the
product: on each run we split the current items into those NEW since the
last successful run and those PREVIOUSLY SEEN. An item counts as new if we
have never seen its (source, source_id), or if its content has changed
(different content_hash) since we last recorded it.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "eos.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
"""


def connect(db_path=DEFAULT_DB_PATH):
    """Open (creating dir + table if needed) the state database."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def content_hash(item):
    """Stable hash of an item's content (identity fields excluded)."""
    payload = {
        "kind": item.kind,
        "title": item.title,
        "due_at_utc": item.due_at_utc.isoformat() if item.due_at_utc else None,
        "starts_at_utc": item.starts_at_utc.isoformat()
        if item.starts_at_utc
        else None,
        "url": item.url,
        "snippet": item.snippet,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def diff(conn, items):
    """Split items into (new, seen) against recorded state. Reads only."""
    new, seen = [], []
    for item in items:
        row = conn.execute(
            "SELECT content_hash FROM seen_items WHERE source = ? AND source_id = ?",
            (item.source, item.source_id),
        ).fetchone()
        if row is None or row[0] != content_hash(item):
            new.append(item)
        else:
            seen.append(item)
    return new, seen


def commit_seen(conn, items, now=None):
    """Record items as seen. first_seen_at is preserved for existing rows;
    only content_hash is refreshed when an item's content changed."""
    now_iso = (now or datetime.now(timezone.utc)).isoformat()
    for item in items:
        conn.execute(
            """
            INSERT INTO seen_items (source, source_id, content_hash, first_seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source, source_id)
            DO UPDATE SET content_hash = excluded.content_hash
            """,
            (item.source, item.source_id, content_hash(item), now_iso),
        )
    conn.commit()
