"""Date math for the 'N years ago today' feature."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from echoledger.config import TIMEZONE


def today(tz_name: str = TIMEZONE) -> date:
    """Return today's calendar date in the given timezone."""
    return datetime.now(ZoneInfo(tz_name)).date()


def years_ago(on_date: date, years: int = 100) -> date:
    """Return the date exactly `years` years before `on_date`.

    Same month and day, year shifted back. The one case that needs special
    handling: if `on_date` is Feb 29 and the target year isn't a leap year,
    Feb 29 doesn't exist that year, so we fall back to Feb 28.
    """
    target_year = on_date.year - years
    try:
        return on_date.replace(year=target_year)
    except ValueError:
        return date(target_year, 2, 28)
