"""state: diff + commit against a throwaway SQLite db. No network."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from eos.normalize import Item
from eos.state import commit_seen, connect, diff


def _item(source_id="canvas-1", title="Problem Set 5", due_day=1):
    return Item(
        source="canvas",
        source_id=source_id,
        kind="assignment",
        title=title,
        due_at_utc=datetime(2099, 12, due_day, 23, 59, tzinfo=timezone.utc),
        starts_at_utc=None,
        url="https://canvas.case.edu/courses/2/assignments/2",
        snippet=None,
    )


@pytest.fixture
def conn(tmp_path):
    # tmp_path keeps every test off the real data/eos.db
    c = connect(tmp_path / "eos.db")
    yield c
    c.close()


def test_first_run_everything_is_new(conn):
    items = [_item("a"), _item("b")]
    new, seen = diff(conn, items)
    assert {i.source_id for i in new} == {"a", "b"}
    assert seen == []


def test_after_commit_items_are_seen(conn):
    items = [_item("a"), _item("b")]
    commit_seen(conn, items)
    new, seen = diff(conn, items)
    assert new == []
    assert {i.source_id for i in seen} == {"a", "b"}


def test_content_change_makes_item_new_again(conn):
    original = _item("a", title="Problem Set 5")
    commit_seen(conn, [original])

    changed = replace(original, title="Problem Set 5 (revised)")
    other = _item("b")  # never seen
    new, seen = diff(conn, [changed, other])
    assert {i.source_id for i in new} == {"a", "b"}
    assert seen == []


def test_first_seen_at_is_preserved_across_content_change(conn):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    original = _item("a", title="v1")
    commit_seen(conn, [original], now=t0)

    changed = replace(original, title="v2")
    commit_seen(conn, [changed], now=t1)

    row = conn.execute(
        "SELECT content_hash, first_seen_at FROM seen_items WHERE source_id = 'a'"
    ).fetchone()
    # hash refreshed to the new content, but first_seen_at unchanged
    assert row[1] == t0.isoformat()
    _, seen = diff(conn, [changed])
    assert len(seen) == 1  # the refreshed hash now matches
