from datetime import date

from echoledger.utils.dates import today, years_ago


def test_years_ago_regular_date() -> None:
    assert years_ago(date(2026, 10, 29), years=100) == date(1926, 10, 29)


def test_years_ago_leap_day_round_trips_when_target_year_is_also_leap() -> None:
    # 1924 is a leap year too, so Feb 29 exists on both ends - no fallback needed.
    assert years_ago(date(2024, 2, 29), years=100) == date(1924, 2, 29)


def test_years_ago_leap_day_falls_back_to_feb_28_when_target_year_is_not_leap() -> None:
    # 1900 is NOT a leap year (divisible by 100 but not 400), so Feb 29, 1900
    # doesn't exist - we fall back to Feb 28.
    assert years_ago(date(2000, 2, 29), years=100) == date(1900, 2, 28)


def test_years_ago_custom_offset() -> None:
    assert years_ago(date(2026, 1, 1), years=10) == date(2016, 1, 1)


def test_today_returns_a_date_in_the_configured_timezone() -> None:
    result = today(tz_name="Asia/Kolkata")
    assert isinstance(result, date)
