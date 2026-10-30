"""Command-line interface: `echoledger fetch` and `echoledger show`."""

from __future__ import annotations

import argparse
from datetime import date

from echoledger.config import DB_PATH, NEWSPAPER_KEY, RAW_DIR
from echoledger.sources.american_stories import ingest_year
from echoledger.sources.rss import FEEDS, fetch_headlines
from echoledger.storage.db import (
    connect,
    get_historical_articles,
    get_today_headlines,
    save_today_headline,
)
from echoledger.utils.dates import today as today_fn
from echoledger.utils.dates import years_ago


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"not a valid date (expected YYYY-MM-DD): {value!r}"
        ) from exc


def cmd_fetch(args: argparse.Namespace) -> None:
    on_date: date = args.date or today_fn()
    historical_date = years_ago(on_date, 100)
    conn = connect(DB_PATH)

    print(f"Fetching for {on_date.isoformat()} (100 years ago: {historical_date.isoformat()})...")

    saved = ingest_year(conn, historical_date.year, NEWSPAPER_KEY, RAW_DIR)
    if saved:
        print(
            f"  Ingested {saved} historical articles for all of {historical_date.year} "
            "(one-time cost - future dates this year won't re-scan the archive)."
        )
    else:
        print(f"  {historical_date.year} already ingested - reading from cache.")

    historical_articles = get_historical_articles(conn, historical_date)
    print(f"  {len(historical_articles)} historical article(s) available for {historical_date}.")

    headline_count = 0
    for source_name, url in FEEDS.items():
        headlines = fetch_headlines(url, source_name=source_name, on_date=on_date, limit=3)
        for headline in headlines:
            save_today_headline(conn, headline)
        headline_count += len(headlines)
        print(f"  Fetched {len(headlines)} headline(s) from {source_name}.")

    conn.close()
    print(f"Done. {len(historical_articles)} historical, {headline_count} today headlines saved.")


def cmd_show(args: argparse.Namespace) -> None:
    on_date: date = args.date or today_fn()
    historical_date = years_ago(on_date, 100)
    conn = connect(DB_PATH)

    print(f"=== {on_date.isoformat()} <-> {historical_date.isoformat()} ===\n")

    print(f"--- 100 Years Ago Today ({historical_date.isoformat()}) ---")
    historical_articles = get_historical_articles(conn, historical_date)
    if not historical_articles:
        print("  (nothing cached yet - run `echoledger fetch` first)")
    else:
        for article in historical_articles[:5]:
            print(f"  [{article.newspaper}, p{article.page}] {article.headline or '(no headline)'}")
        if len(historical_articles) > 5:
            print(f"  ...and {len(historical_articles) - 5} more.")

    print(f"\n--- Today's Top Headlines ({on_date.isoformat()}) ---")
    today_headlines = get_today_headlines(conn, on_date)
    if not today_headlines:
        print("  (nothing cached yet - run `echoledger fetch` first)")
    else:
        for headline in today_headlines:
            print(f"  [{headline.source_name}] {headline.headline}")
            print(f"    {headline.snippet}")
            print(f"    {headline.url}")

    conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="echoledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch and cache data for a date")
    fetch_parser.add_argument("--date", type=_parse_date, default=None)
    fetch_parser.set_defaults(func=cmd_fetch)

    show_parser = subparsers.add_parser("show", help="Show cached data for a date")
    show_parser.add_argument("--date", type=_parse_date, default=None)
    show_parser.set_defaults(func=cmd_show)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
