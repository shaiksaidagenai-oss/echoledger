"""Command-line interface: `echoledger fetch` and `echoledger show`."""

from __future__ import annotations

import argparse
from datetime import date

from echoledger.agents.diary_workflow import run_diary_workflow
from echoledger.api.views import build_daily_view
from echoledger.config import DB_PATH, LLM_MODEL, NEWSPAPER_KEY, RAW_DIR
from echoledger.evals.brier import brier_score
from echoledger.guardrails.injection import detect_injection_markers
from echoledger.llm.news_summary import summarize_headlines
from echoledger.llm.predictions import generate_predictions, resolve_predictions
from echoledger.rag.echo import find_echo_candidates
from echoledger.rag.index import index_historical_articles, index_today_headlines
from echoledger.sources.american_stories import ingest_year
from echoledger.sources.rss import FEEDS, fetch_headlines
from echoledger.storage.db import (
    connect,
    get_diary_entry,
    get_echo_candidates,
    get_historical_articles,
    get_leakage_judgment,
    get_news_summaries,
    get_predictions_created_on,
    get_resolved_predictions,
    save_echo_candidate,
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


def _ask_for_diary_approval(
    entry_text: str, verdict: str | None, violations: list[str], attempt: int, max_attempts: int
) -> str:
    """The real human-in-the-loop step: Arthur's draft is shown right here
    in the terminal, and `fetch` genuinely pauses until you answer.

    A rejection doesn't have to be final - this is the highest-leakage-risk
    content in the project, so "approve a flawed entry or lose the day
    entirely" was too narrow a choice. Offers a real third option:
    regenerate a fresh draft (up to max_attempts total)."""
    print(
        f"\n  === Draft diary entry (attempt {attempt}/{max_attempts}), "
        "awaiting your approval ==="
    )
    print(entry_text)
    print(f"\n  Leakage judge verdict: {verdict}")
    if violations:
        print("  Violations flagged:")
        for violation in violations:
            print(f"    - {violation}")

    can_regenerate = attempt < max_attempts
    options = "[y]es / [n]o" + (" / [r]egenerate" if can_regenerate else "")
    # .strip("﻿...") also strips a leading BOM - some shells (PowerShell's
    # `"y" | command` in particular) prepend one when piping text to stdin,
    # which plain .strip() leaves behind since it isn't whitespace.
    answer = input(f"\n  Approve this entry? {options}: ").strip("﻿ \t\r\n").lower()

    if answer == "y":
        return "approve"
    if answer == "r" and can_regenerate:
        return "regenerate"
    return "reject"


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
            markers = detect_injection_markers(f"{headline.headline} {headline.snippet}")
            if markers:
                print(f"  [guardrail] Possible injection text in headline {headline.id}: {markers}")
        all_headlines.extend(headlines)
        print(f"  Fetched {len(headlines)} headline(s) from {source_name}.")

    # LLM steps - each checks first and skips if already done, so re-running
    # `fetch` for a date you've already processed never spends money twice.
    if get_diary_entry(conn, historical_date) is None:
        print(f"  Arthur is writing his diary entry for {historical_date} ({LLM_MODEL})...")
        entry = run_diary_workflow(
            conn,
            historical_date,
            historical_articles,
            model=LLM_MODEL,
            get_approval=_ask_for_diary_approval,
        )
        status = "approved" if entry.approved else "rejected"
        print(f"  Arthur's diary entry for {historical_date}: {status}.")
    else:
        print(f"  Arthur's diary entry for {historical_date} already exists - skipping.")

    already_summarized = {s.headline_id for s in get_news_summaries(conn, on_date)}
    new_headlines = [h for h in all_headlines if h.id not in already_summarized]
    if new_headlines:
        summarize_headlines(conn, on_date, new_headlines, model=LLM_MODEL)
        print(f"  Summarized {len(new_headlines)} new headline(s).")
    else:
        print("  All of today's headlines already summarized - skipping.")

    # Index for retrieval, then find History Echo matches - both idempotent,
    # so re-running fetch never re-embeds or re-queries unchanged data.
    indexed_historical = index_historical_articles(conn, historical_articles)
    indexed_today = index_today_headlines(conn, all_headlines)
    if indexed_historical or indexed_today:
        print(f"  Indexed {indexed_historical} historical + {indexed_today} today text(s).")

    already_echoed = {c.today_headline_id for c in get_echo_candidates(conn, on_date)}
    headlines_needing_echo = [h for h in all_headlines if h.id not in already_echoed]
    if headlines_needing_echo:
        new_candidates = find_echo_candidates(
            conn, headlines_needing_echo, max_historical_date=historical_date
        )
        for candidate in new_candidates:
            save_echo_candidate(conn, candidate)
        print(f"  Found {len(new_candidates)} new History Echo match(es).")
    else:
        print("  All of today's headlines already have echo matches - skipping.")

    # Predictions: generate today's (idempotent per-day), then resolve
    # anything due - fully automatic per your call, judged only from our
    # own accumulated real news, never Claude's own training knowledge.
    if not get_predictions_created_on(conn, on_date):
        new_predictions = generate_predictions(conn, on_date, all_headlines, model=LLM_MODEL)
        print(f"  Generated {len(new_predictions)} new prediction(s).")
    else:
        print(f"  Prediction(s) for {on_date} already exist - skipping generation.")

    resolutions = resolve_predictions(conn, on_date, model=LLM_MODEL)
    if resolutions:
        print(f"  Resolved {len(resolutions)} due prediction(s).")

    conn.close()
    print(
        f"Done. {len(historical_articles)} historical, "
        f"{len(all_headlines)} today headlines saved."
    )


def cmd_show(args: argparse.Namespace) -> None:
    on_date: date = args.date or today_fn()
    conn = connect(DB_PATH)
    view = build_daily_view(conn, on_date)
    predictions = get_predictions_created_on(conn, on_date)
    judgment = get_leakage_judgment(conn, view.historical_date)
    conn.close()

    print(f"=== {view.date.isoformat()} <-> {view.historical_date.isoformat()} ===\n")

    newspaper = view.historical_newspaper or "the newspaper"
    print(f"--- Arthur's Diary, {view.historical_date.isoformat()} ({newspaper}) ---")
    if view.diary_pending:
        print("  (a draft exists but was not approved - not shown)")
    elif view.diary_entry is None:
        print("  (nothing cached yet - run `echoledger fetch` first)")
    else:
        print(view.diary_entry)
        if judgment is not None and judgment.verdict == "fail":
            print("\n  [!] LEAKAGE WARNING - the automated judge flagged this entry:")
            for violation in judgment.violations:
                print(f"      - {violation}")

    print(f"\n--- Today's Top Headlines ({view.date.isoformat()}) ---")
    if not view.news:
        print("  (nothing cached yet - run `echoledger fetch` first)")
    else:
        for item in view.news:
            print(f"  [{item.source_name}] {item.headline}")
            print(f"    {item.summary}")
            print(f"    {item.url}")
            if item.echo is not None:
                print(
                    f"    Echo [{item.echo.historical_date}]: "
                    f"{item.echo.historical_headline.strip() or '(no headline)'}"
                )

    print(f"\n--- Predictions made on {view.date.isoformat()} ---")
    if not predictions:
        print("  (none)")
    else:
        for p in predictions:
            print(f"  [{p.probability:.0%}] {p.statement} (resolves {p.resolution_date})")


def cmd_scorecard(args: argparse.Namespace) -> None:
    conn = connect(DB_PATH)
    resolved = get_resolved_predictions(conn)
    conn.close()

    score = brier_score(resolved)
    print("=== Prediction Scorecard ===\n")
    if score is None:
        print("Brier score: not enough resolved predictions yet.")
    else:
        print(f"Brier score: {score:.4f} (lower is better, 0=perfect, 0.25=coin-flip)")

    print(f"\n{len(resolved)} resolved prediction(s):")
    for prediction, resolution in resolved:
        print(
            f"  [{resolution.outcome.upper()}] "
            f"(said {prediction.probability:.0%}) {prediction.statement}"
        )
        print(f"    {resolution.reasoning}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="echoledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch and cache data for a date")
    fetch_parser.add_argument("--date", type=_parse_date, default=None)
    fetch_parser.set_defaults(func=cmd_fetch)

    show_parser = subparsers.add_parser("show", help="Show cached data for a date")
    show_parser.add_argument("--date", type=_parse_date, default=None)
    show_parser.set_defaults(func=cmd_show)

    scorecard_parser = subparsers.add_parser(
        "scorecard", help="Show all resolved predictions and the Brier score"
    )
    scorecard_parser.set_defaults(func=cmd_scorecard)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
