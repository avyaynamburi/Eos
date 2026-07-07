"""Central config, read once from .env.

Keeps environment lookups in one place so the rest of the pipeline imports
plain values. No secrets live here — only non-sensitive settings and hosts.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Local Ollama only. NEVER point this at a cloud endpoint (hard constraint).
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
# Non-thinking fallback used when the primary is too slow or leaks reasoning.
# "llama3.2" resolves to the pulled 3B tag. Must also be local.
OLLAMA_FALLBACK_MODEL = os.environ.get("OLLAMA_FALLBACK_MODEL", "llama3.2")

# Times are stored in UTC and rendered in this zone.
LOCAL_TZ = os.environ.get("LOCAL_TZ", "America/New_York")
