"""Hybrid retriever (CLAUDE.md §6).

Pipeline per query:
  1. Metadata pre-filter by knowledge_area (the single biggest precision lever
     — Ch.5-13 map ~1:1 to plan sections), applied *before* search.
  2. Dense (BGE cosine) + sparse (BM25) retrieval.
  3. Reciprocal Rank Fusion (RRF) of the two rankings.
  4. Cross-encoder rerank of the fused top-K down to a small final set.
  5. Parent-section expansion (small-to-big) before returning context.
Every result carries section_path + page range so findings can cite back.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pmo_engine import config
from pmo_engine.retrieval.bm25_index import BM25Index
from pmo_engine.retrieval.reranker import Reranker
from pmo_engine.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str               # the small chunk text
    parent_text: str        # expanded parent-section text (small-to-big)
    metadata: dict[str, Any]
    score: float

    def citation(self) -> str:
        from pmo_engine import config
        m = self.metadata
        ch = m.get("chapter_number", "?")
        ps, pe = m.get("page_start"), m.get("page_end")
        pages = f"p.{ps}" if ps == pe else f"pp.{ps}-{pe}"
        book = config.kb_abbrev(m.get("knowledge_base", ""))
        return f"{book} Ch.{ch} ({m.get('chapter_title','')}), {pages}"


def _rrf_fuse(dense: list[dict], sparse: list[dict], k: int) -> list[dict]:
    """Reciprocal Rank Fusion of two ranked lists keyed by chunk_id."""
    scores: dict[str, float] = {}
    store: dict[str, dict] = {}
    for ranking in (dense, sparse):
        for rank, item in enumerate(ranking):
            cid = item["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            store.setdefault(cid, item)
    fused = []
    for cid, s in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        item = dict(store[cid])
        item["score"] = s
        fused.append(item)
    return fused


class HybridRetriever:
    def __init__(self, vector_store: VectorStore | None = None,
                 bm25: BM25Index | None = None,
                 parent_store: dict[str, str] | None = None) -> None:
        self.vs = vector_store or VectorStore()
        self.bm25 = bm25 or (BM25Index.load() if BM25Index.exists()
                             else BM25Index())
        self.parent_store = parent_store if parent_store is not None \
            else self._load_parents()

    @staticmethod
    def _load_parents(path: Path | None = None) -> dict[str, str]:
        path = Path(path or config.PARENT_STORE_PATH)
        if path.exists():
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        logger.warning("Parent store not found at %s; expansion disabled.", path)
        return {}

    @staticmethod
    def _build_where(knowledge_area: str | list[str] | None,
                     content_types: list[str] | None,
                     extra: dict | None) -> dict | None:
        clauses: list[dict] = []
        if knowledge_area:
            if isinstance(knowledge_area, str):
                clauses.append({"knowledge_area": knowledge_area})
            else:
                clauses.append({"knowledge_area": {"$in": list(knowledge_area)}})
        if content_types:
            clauses.append({"content_type": {"$in": content_types}})
        if extra:
            clauses.append(extra)
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def retrieve(self, query: str,
                 knowledge_area: str | list[str] | None = None,
                 content_types: list[str] | None = None,
                 top_k: int = config.RERANK_TOP_K,
                 shortlist_k: int = config.HYBRID_TOP_K,
                 extra_where: dict | None = None,
                 expand_parent: bool = True) -> list[RetrievedChunk]:
        where = self._build_where(knowledge_area, content_types, extra_where)
        dense = self.vs.query(query, top_k=shortlist_k, where=where)
        sparse = self.bm25.search(query, top_k=shortlist_k, where=where)

        # If a strict KA filter returned almost nothing (e.g. mis-tagged
        # chapter), fall back to an unfiltered search so we never return empty.
        if not dense and not sparse and where is not None:
            logger.info("Filtered retrieval empty for KA=%s; retrying open.",
                        knowledge_area)
            dense = self.vs.query(query, top_k=shortlist_k)
            sparse = self.bm25.search(query, top_k=shortlist_k)

        fused = _rrf_fuse(dense, sparse, config.RRF_K)
        reranked = Reranker.rerank(query, fused, top_k=top_k)

        results: list[RetrievedChunk] = []
        for item in reranked:
            meta = item["metadata"]
            parent = ""
            if expand_parent:
                parent = self.parent_store.get(meta.get("section_path", ""),
                                               item["text"])
            results.append(RetrievedChunk(
                chunk_id=item["chunk_id"], text=item["text"],
                parent_text=parent or item["text"], metadata=meta,
                score=item.get("rerank_score", item.get("score", 0.0))))
        return results

    def multi_query_retrieve(self, queries: list[str],
                             knowledge_area: str | list[str] | None = None,
                             content_types: list[str] | None = None,
                             top_k_per_query: int = config.RERANK_TOP_K
                             ) -> list[RetrievedChunk]:
        """Run several sub-queries (CLAUDE.md §6.3) and dedupe by chunk_id."""
        seen: dict[str, RetrievedChunk] = {}
        for q in queries:
            for rc in self.retrieve(q, knowledge_area=knowledge_area,
                                    content_types=content_types,
                                    top_k=top_k_per_query):
                if rc.chunk_id not in seen or rc.score > seen[rc.chunk_id].score:
                    seen[rc.chunk_id] = rc
        return sorted(seen.values(), key=lambda r: r.score, reverse=True)
