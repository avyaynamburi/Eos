"""Turn structured items into briefing prose with local Ollama.

Division of labor: code builds a deterministic digest and owns every date;
the model only writes connective prose. To make a hallucinated deadline
structurally impossible, the digest handed to the model contains NO exact
dates or times — only code-computed relative buckets (today / this week /
later). Exact dates are interpolated by code downstream in render.
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from eos import config

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "briefing.txt"
_MAX_ITEMS_PER_SECTION = 20
_SNIPPET_CHARS = 160
_THINK_PAIR_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text):
    """Drop qwen3 reasoning. Handles complete <think>...</think> blocks and
    the case where Ollama suppresses the opening tag but leaves a stray
    closing </think> in front of the real answer."""
    text = _THINK_PAIR_RE.sub("", text)
    if "</think>" in text.lower():
        # keep only what follows the last closing tag
        idx = text.lower().rindex("</think>") + len("</think>")
        text = text[idx:]
    return text.strip()


def _bucket(when_local, now_local):
    """Coarse, code-owned timing label. Never a specific date."""
    delta_days = (when_local.date() - now_local.date()).days
    if delta_days <= 0:
        return "today"
    if delta_days <= 7:
        return "this week"
    return "later"


def _digest_line(item, tz, now_local):
    when = item.due_at_utc or item.starts_at_utc
    bucket = _bucket(when.astimezone(tz), now_local)
    verb = "due" if item.kind == "assignment" else "starts"
    line = f"- {item.kind}: {item.title} — {verb} {bucket}"
    if item.snippet:
        snippet = " ".join(item.snippet.split())[:_SNIPPET_CHARS]
        line += f' ("{snippet}")'
    return line


def _format_digest(new_items, other_items, tz_name):
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    lines = [f"Today is {now_local:%A, %B %d, %Y} ({tz_name})."]
    for header, items in (
        ("NEW SINCE LAST RUN", new_items),
        ("ALSO UPCOMING", other_items),
    ):
        capped = items[:_MAX_ITEMS_PER_SECTION]
        lines.append("")
        lines.append(f"{header} ({len(capped)}):")
        if not capped:
            lines.append("- (none)")
        else:
            lines.extend(_digest_line(item, tz, now_local) for item in capped)
    return "\n".join(lines)


def build_prompt(new_items, other_items, tz_name=None):
    """Deterministic prompt assembly. Pure; no network."""
    tz_name = tz_name or config.LOCAL_TZ
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{{DIGEST}}", _format_digest(new_items, other_items, tz_name))


# qwen3 can't be reliably stopped from reasoning on Ollama 0.30.10, so give the
# primary model a bounded budget and fall back to the non-thinking model.
_PRIMARY_TIMEOUT = 90
_FALLBACK_TIMEOUT = 60

_REASONING_OPENERS = (
    "okay", "hmm", "alright", "let me", "we ", "first,", "the user", "so ",
)


def _looks_like_reasoning(text):
    """Heuristic: does this read like leaked chain-of-thought, not an overview?"""
    low = text.lower()
    if "<think>" in low or "</think>" in low:
        return True
    if len(text) > 700:  # a 2-4 sentence overview is short
        return True
    if any(m in low for m in ("the digest", "the rule says", "we must", "we need to")):
        return True
    return low.lstrip().startswith(_REASONING_OPENERS)


class _OllamaUnreachable(Exception):
    """The Ollama server itself could not be contacted (vs. a slow model)."""


def _generate(model, prompt, timeout):
    """One Ollama call. Returns cleaned text, or None if it timed out / errored.
    Raises _OllamaUnreachable only when the server is down."""
    try:
        response = requests.post(
            f"{config.OLLAMA_HOST}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "think": False,  # honored by non-thinking models; harmless else
                "options": {"temperature": 0.2},
            },
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.ConnectionError:
        raise _OllamaUnreachable
    except requests.RequestException:
        return None  # timeout or HTTP error -> let the caller fall back
    return _strip_thinking(response.json().get("response", ""))


def summarize(new_items, other_items, tz_name=None):
    """Build the prompt and return an overview, trying the primary model first
    and falling back to the non-thinking model if it is slow or reasons out loud."""
    prompt = build_prompt(new_items, other_items, tz_name)
    try:
        text = _generate(config.OLLAMA_MODEL, prompt, _PRIMARY_TIMEOUT)
        if text and not _looks_like_reasoning(text):
            print(f"summarized with {config.OLLAMA_MODEL}", file=sys.stderr)
            return text

        reason = "too slow" if text is None else "leaked reasoning"
        print(
            f"{config.OLLAMA_MODEL} {reason}; falling back to "
            f"{config.OLLAMA_FALLBACK_MODEL}",
            file=sys.stderr,
        )
        fallback = _generate(config.OLLAMA_FALLBACK_MODEL, prompt, _FALLBACK_TIMEOUT)
    except _OllamaUnreachable:
        sys.exit(
            f"Could not reach local Ollama at {config.OLLAMA_HOST}. "
            "Is it running (`ollama serve`)?"
        )

    if fallback is None:
        sys.exit(
            f"Both {config.OLLAMA_MODEL} and {config.OLLAMA_FALLBACK_MODEL} "
            "failed (timeout or model not pulled)."
        )
    print(f"summarized with {config.OLLAMA_FALLBACK_MODEL}", file=sys.stderr)
    return fallback
