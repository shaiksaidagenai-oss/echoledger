"""Project-wide configuration, loaded from environment variables / .env."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Timezone used whenever we need to know "today's date" (e.g. Asia/Kolkata means
# the date rolls over at local midnight in India, not UTC midnight).
TIMEZONE = os.getenv("ECHOLEDGER_TIMEZONE", "Asia/Kolkata")
