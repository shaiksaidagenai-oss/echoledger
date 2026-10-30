"""Command-line interface: `echoledger fetch` and `echoledger show`."""

from __future__ import annotations

import argparse
from datetime import date

from echoledger.api.views import build_daily_view
from echoledger.config import DB_PATH, LLM_MODEL, NEWSPAPER_KEY, RAW_DIR
from echoledger.llm.arthur import write_diary_entry
from echoledger.llm.news_summary import summarize_headlines
from echoledger.sources.american_stories import ingest_year
from echoledger.sources.rss import FEEDS, fetch_headlines
from echoledger.storage.db import (
    connect,
    get_diary_entry,
    get_historical_articles,
    get_news_summaries,
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

    all_headlines = []
    for source_name, url in FEEDS.items():
        headlines = fetch_headlines(url, source_name=source_name, on_date=on_date, limit=3)
        for headline in headlines:
            save_today_headline(conn, headline)
        all_headlines.extend(headlines)
        print(f"  Fetched {len(headlines)} headline(s) from {source_name}.")

    # LLM steps - each checks first and skips if already done, so re-running
    # `fetch` for a date you've already processed never spends money twice.
    if get_diary_entry(conn, historical_date) is None:
        write_diary_entry(conn, historical_date, historical_articles, model=LLM_MODEL)
        print(f"  Arthur wrote his diary entry for {historical_date} ({LLM_MODEL}).")
    else:
        print(f"  Arthur's diary entry for {historical_date} already exists - skipping.")

    already_summarized = {s.headline_id for s in get_news_summaries(conn, on_date)}
    new_headlines = [h for h in all_headlines if h.id not in already_summarized]
    if new_headlines:
        summarize_headlines(conn, on_date, new_headlines, model=LLM_MODEL)
        print(f"  Summarized {len(new_headlines)} new headline(s).")
    else:
        print("  All of today's headlines already summarized - skipping.")

    conn.close()
    print(
        f"Done. {len(historical_articles)} historical, "
        f"{len(all_headlines)} today headlines saved."
    )


def cmd_show(args: argparse.Namespace) -> None:
    on_date: date = args.date or today_fn()
    conn = connect(DB_PATH)
    view = build_daily_view(conn, on_date)
    conn.close()

    print(f"=== {view.date.isoformat()} <-> {view.historical_date.isoformat()} ===\n")

    newspaper = view.historical_newspaper or "the newspaper"
    print(f"--- Arthur's Diary, {view.historical_date.isoformat()} ({newspaper}) ---")
    if view.diary_entry is None:
        print("  (nothing cached yet - run `echoledger fetch` first)")
    else:
        print(view.diary_entry)

    print(f"\n--- Today's Top Headlines ({view.date.isoformat()}) ---")
    if not view.news:
        print("  (nothing cached yet - run `echoledger fetch` first)")
    else:
        for item in view.news:
            print(f"  [{item.source_name}] {item.headline}")
            print(f"    {item.summary}")
            print(f"    {item.url}")


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
