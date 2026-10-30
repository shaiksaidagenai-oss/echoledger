import io
import json
import os
import sqlite3
import tarfile
from datetime import date
from pathlib import Path

import pytest

from echoledger.sources.american_stories import (
    NEWSPAPER_LCCNS,
    ingest_year,
    iter_newspaper_scans,
    parse_scan,
)
from echoledger.storage.db import (
    connect,
    get_historical_articles,
    is_year_ingested,
    mark_year_ingested,
)


def test_parse_scan_groups_headline_and_body_by_full_article_id() -> None:
    scan = {
        "bboxes": [
            {
                "class": "headline",
                "raw_text": "OPENS FIGHT ON\n: PHONE RATES",
                "legibility": "Legible",
                "full_article_id": 1,
            },
            {
                "class": "article",
                "raw_text": "The fight of the Chesapeake and Potomac Telephone Company...",
                "legibility": "Legible",
                "full_article_id": 1,
                "reading_order_id": 0,
            },
        ]
    }

    articles = parse_scan(scan)

    assert articles == [
        {
            "headline": "OPENS FIGHT ON\n: PHONE RATES",
            "text": "The fight of the Chesapeake and Potomac Telephone Company...",
        }
    ]


def test_parse_scan_drops_articles_with_no_legible_text() -> None:
    scan = {
        "bboxes": [
            {
                "class": "article",
                "raw_text": "mostly unreadable garble",
                "legibility": "Questionable",
                "full_article_id": 2,
            },
        ]
    }

    assert parse_scan(scan) == []


def test_parse_scan_ignores_boxes_with_no_article_id() -> None:
    scan = {
        "bboxes": [
            {"class": "article", "raw_text": "stray text", "legibility": "Legible"},
        ]
    }

    assert parse_scan(scan) == []


def test_parse_scan_joins_multi_column_body_in_reading_order() -> None:
    scan = {
        "bboxes": [
            {
                "class": "article",
                "raw_text": "second column text",
                "legibility": "Legible",
                "full_article_id": 3,
                "reading_order_id": 1,
            },
            {
                "class": "article",
                "raw_text": "first column text",
                "legibility": "Legible",
                "full_article_id": 3,
                "reading_order_id": 0,
            },
        ]
    }

    articles = parse_scan(scan)

    assert articles == [{"headline": "", "text": "first column text\n\nsecond column text"}]


def _make_fake_tar(tmp_path: str, entries: dict[str, dict[str, object]]) -> str:
    tar_path = f"{tmp_path}/fake.tar.gz"
    with tarfile.open(tar_path, mode="w:gz") as tar:
        for name, content in entries.items():
            data = json.dumps(content).encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return tar_path


def test_iter_newspaper_scans_filters_by_lccn_and_parses_filename(tmp_path: Path) -> None:
    tar_path = _make_fake_tar(
        str(tmp_path),
        {
            "faro_1999/1999-01-01_p1_sn11111111_xxx.json": {"bboxes": []},
            "faro_1999/1999-01-01_p3_sn22222222_xxx.json": {"bboxes": []},
        },
    )

    results = list(iter_newspaper_scans(tar_path, lccn="sn11111111"))

    assert results == [("1999-01-01", 1, {"bboxes": []})]


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def test_ingest_year_saves_articles_and_marks_year_done(
    tmp_path: Path, conn: sqlite3.Connection
) -> None:
    lccn = NEWSPAPER_LCCNS["evening_star"]
    scan_with_one_article = {
        "bboxes": [
            {
                "class": "headline",
                "raw_text": "A HEADLINE",
                "legibility": "Legible",
                "full_article_id": 1,
            },
            {
                "class": "article",
                "raw_text": "Some legible article body.",
                "legibility": "Legible",
                "full_article_id": 1,
                "reading_order_id": 0,
            },
        ]
    }
    raw_dir = str(tmp_path)
    _make_fake_tar(
        raw_dir,
        {f"faro_1926/1926-10-29_p1_{lccn}_xxx.json": scan_with_one_article},
    )
    # ingest_year expects the file named faro_<year>.tar.gz exactly:
    os.replace(f"{raw_dir}/fake.tar.gz", f"{raw_dir}/faro_1926.tar.gz")

    saved_count = ingest_year(conn, 1926, "evening_star", raw_dir)

    assert saved_count == 1
    assert is_year_ingested(conn, 1926, "evening_star") is True
    articles = get_historical_articles(conn, date(1926, 10, 29))
    assert len(articles) == 1
    assert articles[0].headline == "A HEADLINE"
    assert articles[0].newspaper == "Evening Star"


def test_ingest_year_is_a_no_op_if_already_done(tmp_path: Path, conn: sqlite3.Connection) -> None:
    mark_year_ingested(conn, 1926, "evening_star")

    # No tar.gz file exists here at all - if ingest_year tried to read it,
    # this would raise. Returning 0 immediately proves it skipped the work.
    saved_count = ingest_year(conn, 1926, "evening_star", str(tmp_path))

    assert saved_count == 0
