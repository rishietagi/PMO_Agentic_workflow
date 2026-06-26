"""Local BM25 sparse index (CLAUDE.md §3/§6).

PM terminology (WBS, EVM, RACI, ITTO, specific PMI terms) needs exact-match
retrieval alongside semantic search. Persisted as a pickle next to the Chroma
store so it rebuilds in lockstep with the vector store.
"""
from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path
from typing import Any

from pmo_engine import config

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class BM25Index:
    def __init__(self) -> None:
        self._bm25 = None
        self.chunk_ids: list[str] = []
        self.metadatas: list[dict[str, Any]] = []
        self.texts: list[str] = []

    def build(self, chunk_ids: list[str], texts: list[str],
              metadatas: list[dict[str, Any]],
              embed_texts: list[str] | None = None) -> None:
        from rank_bm25 import BM25Okapi
        self.chunk_ids = chunk_ids
        self.texts = texts            # clean text for display
        self.metadatas = metadatas
        # tokenize breadcrumb+body so KA/section/acronym terms boost sparse hits
        corpus = [tokenize(t) for t in (embed_texts or texts)]
        self._bm25 = BM25Okapi(corpus)
        logger.info("Built BM25 index over %d docs.", len(texts))

    def save(self, path: Path | None = None) -> None:
        path = Path(path or config.BM25_INDEX_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({
                "bm25": self._bm25, "chunk_ids": self.chunk_ids,
                "metadatas": self.metadatas, "texts": self.texts}, f)
        logger.info("Saved BM25 index -> %s", path)

    @classmethod
    def load(cls, path: Path | None = None) -> "BM25Index":
        path = Path(path or config.BM25_INDEX_PATH)
        obj = cls()
        with path.open("rb") as f:
            data = pickle.load(f)
        obj._bm25 = data["bm25"]
        obj.chunk_ids = data["chunk_ids"]
        obj.metadatas = data["metadatas"]
        obj.texts = data["texts"]
        return obj

    @staticmethod
    def exists(path: Path | None = None) -> bool:
        return Path(path or config.BM25_INDEX_PATH).exists()

    def search(self, query: str, top_k: int,
               where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out: list[dict[str, Any]] = []
        for i in idx:
            if len(out) >= top_k:
                break
            meta = self.metadatas[i]
            if where and not _meta_match(meta, where):
                continue
            if scores[i] <= 0:
                continue
            out.append({
                "chunk_id": self.chunk_ids[i],
                "text": self.texts[i],
                "metadata": meta,
                "score": float(scores[i]),
            })
        return out


def _meta_match(meta: dict[str, Any], where: dict[str, Any]) -> bool:
    """Minimal Chroma-style where matcher: equality and {'$in': [...]}."""
    for key, cond in where.items():
        if key in ("$and", "$or"):
            subs = [_meta_match(meta, c) for c in cond]
            if key == "$and" and not all(subs):
                return False
            if key == "$or" and not any(subs):
                return False
            continue
        val = meta.get(key)
        if isinstance(cond, dict):
            if "$in" in cond and val not in cond["$in"]:
                return False
            if "$ne" in cond and val == cond["$ne"]:
                return False
        elif val != cond:
            return False
    return True
