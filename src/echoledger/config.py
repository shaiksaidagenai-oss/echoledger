"""Project-wide configuration, loaded from environment variables / .env."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Timezone used whenever we need to know "today's date" (e.g. Asia/Kolkata means
# the date rolls over at local midnight in India, not UTC midnight).
TIMEZONE = os.getenv("ECHOLEDGER_TIMEZONE", "Asia/Kolkata")

# Where downloaded/cached data and the SQLite database live. Gitignored.
DATA_DIR = os.getenv("ECHOLEDGER_DATA_DIR", "data")
RAW_DIR = f"{DATA_DIR}/raw"
DB_PATH = f"{DATA_DIR}/echoledger.db"

# Which newspaper (see sources/american_stories.py) and feeds (see sources/rss.py)
# Arthur and "Today's Top 10" use.
NEWSPAPER_KEY = "evening_star"

# Which Claude model writes Arthur's diary + news summaries (configurable per
# the project's cost-control rule - see llm/client.py for per-model pricing).
LLM_MODEL = os.getenv("ECHOLEDGER_LLM_MODEL", "claude-haiku-4-5")
