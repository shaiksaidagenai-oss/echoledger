"""Fetch today's headlines from RSS feeds, as short snippets only.

RSS descriptions sometimes carry more text than we want to keep, so we
enforce a hard snippet length in code rather than trusting the feed -
our copyright rule requires headline + short snippet + link, never more.
"""

from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

import httpx

from echoledger.models import TodayHeadline

FEEDS = {
    "BBC News": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "The Guardian": "https://www.theguardian.com/world/rss",
    "NPR": "https://feeds.npr.org/1004/rss.xml",
}

MAX_SNIPPET_LENGTH = 300

_USER_AGENT = "EchoLedger/0.1 (learning project; contact automation.vali@gmail.com)"


def _strip_html(text: str) -> str:
    """'<p>Foo &amp; bar</p>' -> 'Foo & bar'."""
    without_tags = re.sub(r"<[^>]+>", "", text)
    return html.unescape(without_tags).strip()


def _make_snippet(description: str) -> str:
    text = _strip_html(description)
    if len(text) <= MAX_SNIPPET_LENGTH:
        return text
    return text[:MAX_SNIPPET_LENGTH].rsplit(" ", 1)[0] + "..."


def _id_from_url(source_name: str, url: str) -> str:
    slug = source_name.lower().replace(" ", "-")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"{slug}-{digest}"


def parse_feed_xml(
    xml_text: str,
    *,
    source_name: str,
    on_date: date,
    fetched_at: datetime,
    limit: int = 3,
) -> list[TodayHeadline]:
    """Pure parsing step, no network - easy to test with a fixed XML string."""
    root = ET.fromstring(xml_text)
    headlines = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = item.findtext("description") or ""

        headlines.append(
            TodayHeadline(
                id=_id_from_url(source_name, link),
                date=on_date,
                source_name=source_name,
                headline=title,
                snippet=_make_snippet(description),
                url=link,
                fetched_at=fetched_at,
            )
        )
    return headlines


def fetch_headlines(
    url: str,
    *,
    source_name: str,
    on_date: date,
    limit: int = 3,
    client: httpx.Client | None = None,
) -> list[TodayHeadline]:
    """Fetch and parse one RSS feed. Pass `client` (e.g. with a MockTransport)
    to test this without hitting the network."""
    owns_client = client is None
    if client is None:
        client = httpx.Client(headers={"User-Agent": _USER_AGENT}, timeout=10.0)
    try:
        response = client.get(url)
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return parse_feed_xml(
        response.text,
        source_name=source_name,
        on_date=on_date,
        fetched_at=datetime.now(),
        limit=limit,
    )
