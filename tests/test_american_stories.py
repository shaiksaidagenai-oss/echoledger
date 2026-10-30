import io
import json
import tarfile
from pathlib import Path

from echoledger.sources.american_stories import iter_newspaper_scans, parse_scan


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
