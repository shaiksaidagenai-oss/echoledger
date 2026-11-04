"""History Echo: for each of today's headlines, find the most similar
historical article - restricted to articles dated on or before Arthur's
own historical date, so a match can never leak a future-to-Arthur article.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from chromadb.api.models.Collection import Collection
from openai import OpenAI
from pydantic import BaseModel

from echoledger.models import TodayHeadline
from echoledger.rag.embeddings import embed_texts
from echoledger.rag.vector_store import get_collection


class EchoCandidate(BaseModel):
    today_headline_id: str
    today_headline_text: str
    historical_article_id: str
    historical_headline: str
    historical_date: date
    distance: float


def find_echo_candidates(
    conn: sqlite3.Connection,
    headlines: list[TodayHeadline],
    max_historical_date: date,
    client: OpenAI | None = None,
    collection: Collection | None = None,
) -> list[EchoCandidate]:
    if not headlines:
        return []

    if collection is None:
        collection = get_collection()
    max_date_int = int(max_historical_date.isoformat().replace("-", ""))

    query_embeddings = embed_texts(
        conn, [h.headline for h in headlines], purpose="embed_echo_query", client=client
    )

    results = collection.query(
        query_embeddings=query_embeddings,  # type: ignore[arg-type]
        n_results=1,
        # Verified working at runtime (2026-11-04): Chroma accepts bare
        # equality shorthand inside $and, even though chromadb's type
        # stubs are stricter than what the API actually accepts.
        where={"$and": [{"kind": "historical"}, {"date_int": {"$lte": max_date_int}}]},  # type: ignore[dict-item]
    )

    # We didn't restrict `include=`, so ids/documents/metadatas/distances are
    # always populated - the stub marks them Optional because other calls
    # (e.g. with include=["documents"] only) could omit some of them.
    assert results["ids"] is not None
    assert results["documents"] is not None
    assert results["metadatas"] is not None
    assert results["distances"] is not None

    candidates = []
    for i, headline in enumerate(headlines):
        matched_ids = results["ids"][i]
        if not matched_ids:
            continue
        metadata = results["metadatas"][i][0]
        historical_date_str = metadata["date"]
        assert isinstance(historical_date_str, str)
        candidates.append(
            EchoCandidate(
                today_headline_id=headline.id,
                today_headline_text=headline.headline,
                historical_article_id=matched_ids[0],
                historical_headline=results["documents"][i][0],
                historical_date=date.fromisoformat(historical_date_str),
                distance=results["distances"][i][0],
            )
        )
    return candidates
