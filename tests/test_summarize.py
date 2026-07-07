"""summarize: deterministic prompt building only. No network / no Ollama.

Per the testing policy there are no assertions on model prose here; we only
test the code-owned digest, bucketing, and date-safety guarantee.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from eos.normalize import Item
from eos.summarize import (
    _bucket,
    _looks_like_reasoning,
    _strip_thinking,
    build_prompt,
)

TZ = "America/New_York"


def _assignment(title, due):
    return Item(
        source="canvas",
        source_id=title,
        kind="assignment",
        title=title,
        due_at_utc=due,
        starts_at_utc=None,
        url=None,
        snippet=None,
    )


def test_bucket_labels_are_relative():
    now = datetime(2026, 7, 6, 9, 0, tzinfo=ZoneInfo(TZ))
    assert _bucket(now, now) == "today"
    assert _bucket(now.replace(day=9), now) == "this week"
    assert _bucket(now.replace(day=31), now) == "later"


def test_digest_lists_new_then_upcoming():
    new = [_assignment("PS5", datetime(2099, 12, 1, tzinfo=timezone.utc))]
    other = [_assignment("Essay", datetime(2099, 12, 2, tzinfo=timezone.utc))]
    prompt = build_prompt(new, other, tz_name=TZ)
    assert prompt.index("NEW SINCE LAST RUN") < prompt.index("ALSO UPCOMING")
    assert "PS5" in prompt and "Essay" in prompt


def test_digest_contains_no_exact_dates_only_buckets():
    # the date-safety guarantee: buckets appear, ISO/clock dates never do
    new = [_assignment("PS5", datetime(2099, 12, 1, 23, 59, tzinfo=timezone.utc))]
    prompt = build_prompt(new, [], tz_name=TZ)
    assert "this week" in prompt or "later" in prompt or "today" in prompt
    assert "2099-12-01" not in prompt
    assert "23:59" not in prompt


def test_empty_sections_render_none():
    prompt = build_prompt([], [], tz_name=TZ)
    assert "NEW SINCE LAST RUN (0):" in prompt
    assert "- (none)" in prompt


def test_strip_thinking_handles_full_block():
    assert _strip_thinking("<think>reasoning</think>Final answer.") == "Final answer."


def test_strip_thinking_handles_stray_closing_tag():
    # the exact failure mode seen live: opening tag suppressed, answer trails
    raw = "We are given a digest...\nLet me write.\n</think>\n\nNothing new today."
    assert _strip_thinking(raw) == "Nothing new today."


def test_strip_thinking_leaves_clean_text_untouched():
    assert _strip_thinking("Just prose.") == "Just prose."


def test_reasoning_detector_flags_leaks():
    assert _looks_like_reasoning("Okay, the user wants a short overview.")
    assert _looks_like_reasoning("We need to summarize the digest first.")
    assert _looks_like_reasoning("...stuff</think> Real answer.")
    assert _looks_like_reasoning("word " * 200)  # far too long for an overview


def test_reasoning_detector_passes_clean_overview():
    clean = "You have a busy week ahead with two problem sets due soon."
    assert not _looks_like_reasoning(clean)
