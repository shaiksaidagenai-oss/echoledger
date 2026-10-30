"""Parse "American Stories" scan-level JSON into article text.

Each scan JSON file is one whole newspaper page. Its `bboxes` list holds many
small text regions (headline, article body, etc.) tagged with a shared
`full_article_id` that groups the pieces belonging to one logical article
together, plus a `legibility` tag ("Legible" / "Questionable") per piece.
"""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from typing import Any

# Library of Congress identifiers (LCCN) for newspapers we've chosen to use.
NEWSPAPER_LCCNS = {
    "evening_star": "sn83045462",
}


def parse_scan(scan: dict[str, Any]) -> list[dict[str, str]]:
    """Turn one page's bboxes into a list of {"headline", "text"} articles.

    Only legible text is kept. An article with no legible body text at all
    is dropped - there's nothing usable to show.
    """
    groups: dict[int, list[dict[str, Any]]] = {}
    for box in scan.get("bboxes", []):
        article_id = box.get("full_article_id")
        if article_id is None:
            continue
        groups.setdefault(article_id, []).append(box)

    articles: list[dict[str, str]] = []
    for boxes in groups.values():
        legible = [b for b in boxes if b.get("legibility") == "Legible"]

        body_pieces = sorted(
            (b for b in legible if b.get("class") == "article"),
            key=lambda b: b.get("reading_order_id", 0),
        )
        text = "\n\n".join(b["raw_text"].strip() for b in body_pieces if b.get("raw_text"))
        if not text:
            continue

        headline_pieces = [b for b in legible if b.get("class") == "headline"]
        headline = " ".join(b["raw_text"].strip() for b in headline_pieces if b.get("raw_text"))

        articles.append({"headline": headline, "text": text})

    return articles


def iter_newspaper_scans(tar_path: str, lccn: str) -> Iterator[tuple[str, int, dict[str, Any]]]:
    """Yield (date_str, page_number, scan_json) for every scan of one
    newspaper in a year's tar.gz, without extracting the whole archive.

    Filters by filename first (cheap) before parsing JSON (slower), since
    most files in the archive belong to newspapers we don't want.
    """
    import json

    needle = f"_{lccn}_"
    with tarfile.open(tar_path, mode="r:gz") as tar:
        for member in tar:
            if needle not in member.name or not member.name.endswith(".json"):
                continue
            # Filename looks like: faro_1926/1926-10-29_p1_sn83045462_....json
            filename = member.name.rsplit("/", 1)[-1]
            date_str, page_part = filename.split("_", 2)[:2]
            page_number = int(page_part.removeprefix("p"))

            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            scan = json.loads(extracted.read())
            yield date_str, page_number, scan
