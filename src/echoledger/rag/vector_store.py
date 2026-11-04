"""Chroma vector store - persists to disk under data/chroma/ (gitignored),
same "cache everything" principle as the SQLite database."""

from __future__ import annotations

import chromadb
from chromadb.api.models.Collection import Collection

from echoledger.config import DATA_DIR

COLLECTION_NAME = "echoledger"


def get_collection(path: str = f"{DATA_DIR}/chroma") -> Collection:
    """`path` is overridable so tests can point at a temp directory
    instead of the real on-disk store."""
    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(COLLECTION_NAME)
