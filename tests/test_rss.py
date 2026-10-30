from datetime import date, datetime

import httpx

from echoledger.sources.rss import _make_snippet, fetch_headlines, parse_feed_xml

SAMPLE_FEED = """<?xml version="1.0"?>
<rss><channel>
<item>
  <title>First headline</title>
  <link>https://example.com/story-1</link>
  <description>&lt;p&gt;A short description with &amp; an entity.&lt;/p&gt;</description>
</item>
<item>
  <title>Second headline</title>
  <link>https://example.com/story-2</link>
  <description>Another description.</description>
</item>
<item>
  <title>Third headline (should be cut off by limit)</title>
  <link>https://example.com/story-3</link>
  <description>Yet another.</description>
</item>
</channel></rss>
"""


def test_make_snippet_strips_html_and_decodes_entities() -> None:
    assert _make_snippet("<p>A &amp; B</p>") == "A & B"


def test_make_snippet_truncates_long_text() -> None:
    long_text = "word " * 100  # way over MAX_SNIPPET_LENGTH
    snippet = _make_snippet(long_text)
    assert len(snippet) <= 303  # 300 + "..."
    assert snippet.endswith("...")


def test_parse_feed_xml_respects_limit() -> None:
    headlines = parse_feed_xml(
        SAMPLE_FEED,
        source_name="Test Source",
        on_date=date(2026, 10, 30),
        fetched_at=datetime(2026, 10, 30, 9, 0, 0),
        limit=2,
    )

    assert len(headlines) == 2
    assert headlines[0].headline == "First headline"
    assert headlines[0].snippet == "A short description with & an entity."
    assert headlines[0].url == "https://example.com/story-1"
    assert headlines[0].source_name == "Test Source"
    assert headlines[0].date == date(2026, 10, 30)


def test_parse_feed_xml_same_url_gives_same_id() -> None:
    first, second = parse_feed_xml(
        SAMPLE_FEED,
        source_name="Test Source",
        on_date=date(2026, 10, 30),
        fetched_at=datetime(2026, 10, 30, 9, 0, 0),
        limit=2,
    )
    again = parse_feed_xml(
        SAMPLE_FEED,
        source_name="Test Source",
        on_date=date(2026, 10, 30),
        fetched_at=datetime(2026, 10, 30, 9, 0, 0),
        limit=1,
    )[0]

    assert first.id == again.id
    assert first.id != second.id


def test_fetch_headlines_uses_mocked_http_no_real_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://fake.feed/rss.xml"
        return httpx.Response(200, text=SAMPLE_FEED)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))

    headlines = fetch_headlines(
        "https://fake.feed/rss.xml",
        source_name="Mocked Source",
        on_date=date(2026, 10, 30),
        limit=1,
        client=mock_client,
    )

    assert len(headlines) == 1
    assert headlines[0].headline == "First headline"
