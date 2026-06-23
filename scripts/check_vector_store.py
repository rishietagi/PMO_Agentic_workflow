"""Quick 'is the knowledge base already built?' check (CLAUDE.md §2 rule 4).

Future sessions / the app call this before deciding to (re)run the expensive
ingestion. Exit code 0 = built & usable, 1 = not built.
"""
from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pmo_engine import config  # noqa: E402
from pmo_engine.retrieval.bm25_index import BM25Index  # noqa: E402
from pmo_engine.retrieval.vector_store import VectorStore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("check_vector_store")


def status() -> dict:
    vs = VectorStore()
    count = vs.count()
    bm25_ok = BM25Index.exists()
    parents_ok = config.PARENT_STORE_PATH.exists()
    content_types: Counter = Counter()
    if count:
        data = vs.get_all()
        for m in data.get("metadatas", []) or []:
            content_types[m.get("content_type", "?")] += 1
    return {
        "chroma_chunks": count,
        "bm25_index": bm25_ok,
        "parent_store": parents_ok,
        "content_types": dict(content_types),
        "built": count > 0 and bm25_ok and parents_ok,
    }


def main() -> int:
    s = status()
    logger.info("Chroma chunks : %s", s["chroma_chunks"])
    logger.info("BM25 index    : %s", "present" if s["bm25_index"] else "MISSING")
    logger.info("Parent store  : %s", "present" if s["parent_store"] else "MISSING")
    if s["content_types"]:
        logger.info("Content types : %s", s["content_types"])
    if s["built"]:
        logger.info("STATUS: knowledge base is BUILT — skip ingestion.")
        return 0
    logger.info("STATUS: knowledge base NOT built — run ingest_book.py then "
                "build_vector_store.py.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
