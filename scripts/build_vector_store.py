"""Phase 2 — Build the combined vector store + BM25 index + parent store.

Multi-book: ingests every knowledge base in config.KNOWLEDGE_BASES that has a
structured-elements JSON on disk (RITA from marker OCR, PMBOK from text
extraction), chunks each with its own chapter map, embeds with local BGE
(on GPU when available) into one ChromaDB collection tagged by knowledge_base,
builds a combined BM25 index, persists parent sections, and writes one
chapter-summary chunk per (book, chapter).

Idempotent: refuses to rebuild a populated store unless --rebuild is passed.
Chapter summaries are LLM-written when keys are present, else extractive
placeholders (flagged); regenerate with --refresh-summaries.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pmo_engine import config  # noqa: E402
from pmo_engine.chunking.hierarchical_chunker import (Chunk,  # noqa: E402
                                                      HierarchicalChunker)
from pmo_engine.ocr import extract_structure as es  # noqa: E402
from pmo_engine.retrieval.bm25_index import BM25Index  # noqa: E402
from pmo_engine.retrieval.vector_store import VectorStore  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_vector_store")

# Which structured-elements JSON feeds each knowledge base.
STRUCTURED_JSONS: dict[str, Path] = {
    "RITA_10th_Edition": config.PROCESSED_DIR / "rita_structured.json",
    "PMBOK_Guide_6th": config.PROCESSED_DIR / "pmbok_structured.json",
}


def _chapter_texts(chunks: list[Chunk]) -> dict[int, str]:
    by_ch: dict[int, list[str]] = {}
    for c in chunks:
        if c.chapter_number and c.content_type != "endnote":
            by_ch.setdefault(c.chapter_number, []).append(c.text)
    return {ch: "\n\n".join(parts) for ch, parts in by_ch.items()}


def _llm_chapter_summary(router, book: str, title: str, body: str) -> str:
    from pmo_engine.llm.router import TaskTier
    system = ("You summarize project-management reference chapters for a PMO "
              "knowledge base. Write 3-5 factual sentences capturing the "
              "chapter's key processes, deliverables, and terms. No preamble.")
    user = f"Book: {book}\nChapter: {title}\n\nContent (excerpt):\n{body[:6000]}"
    return router.complete(system, user, tier=TaskTier.REASONING,
                           temperature=0.2, max_tokens=300).strip()


def _extractive_summary(title: str, body: str) -> str:
    import re
    sents = re.split(r"(?<=[.!?])\s+", body.strip())
    sents = [s.strip() for s in sents if len(s.strip()) > 40]
    head = " ".join(sents[:4])
    return (f"[Extractive placeholder - regenerate with an LLM] Chapter "
            f"'{title}'. {head}")[:1200]


def build_chapter_summaries(chunks: list[Chunk], chapter_map: dict,
                            kb_name: str) -> list[Chunk]:
    chap_texts = _chapter_texts(chunks)
    summaries: list[Chunk] = []
    use_llm = config.groq_key_present() or config.google_key_present()
    router = None
    if use_llm:
        from pmo_engine.llm.router import get_router
        router = get_router()
    else:
        logger.warning("NO API KEY: writing EXTRACTIVE chapter summaries for "
                       "%s (regenerate with --refresh-summaries).", kb_name)
    abbr = config.kb_abbrev(kb_name).lower()
    for ch in sorted(chap_texts):
        meta = chapter_map.get(ch, {})
        title = meta.get("title", f"Chapter {ch}")
        ka = meta.get("knowledge_area", "cross_cutting")
        body = chap_texts[ch]
        if use_llm:
            try:
                text = _llm_chapter_summary(router, kb_name, title, body)
                method = "llm"
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM summary failed for %s Ch.%s (%s); extractive.",
                               kb_name, ch, exc)
                text, method = _extractive_summary(title, body), "extractive"
        else:
            text, method = _extractive_summary(title, body), "extractive"
        summaries.append(Chunk(
            chunk_id=f"{abbr}_summary_ch{ch:02d}", text=text, chapter_number=ch,
            chapter_title=title, knowledge_area=ka,
            section_path=f"Ch.{ch} {title} > Chapter Summary",
            page_start=0, page_end=0, content_type="chapter_summary",
            process_group="", knowledge_base=kb_name, summary_method=method))
    logger.info("  %s: %d chapter summaries (%s)", kb_name, len(summaries),
                "llm" if use_llm else "extractive")
    return summaries


def _chunk_book(kb_name: str, json_path: Path):
    profile = config.KNOWLEDGE_BASES[kb_name]
    elements = es.load_elements(json_path)
    logger.info("%s: loaded %d structured elements.", kb_name, len(elements))
    chunker = HierarchicalChunker(chapter_map=profile["chapter_map"],
                                  knowledge_base=kb_name)
    chunks, parents = chunker.chunk(elements)
    summaries = build_chapter_summaries(chunks, profile["chapter_map"], kb_name)
    return chunks + summaries, parents


def _available_books() -> list[tuple[str, Path]]:
    return [(kb, p) for kb, p in STRUCTURED_JSONS.items() if p.exists()]


def refresh_summaries_only() -> int:
    vs = VectorStore()
    if vs.count() == 0:
        logger.error("No populated store; run a full build first.")
        return 1
    for kb_name, json_path in _available_books():
        profile = config.KNOWLEDGE_BASES[kb_name]
        chunks, _ = HierarchicalChunker(
            chapter_map=profile["chapter_map"], knowledge_base=kb_name
        ).chunk(es.load_elements(json_path))
        summaries = build_chapter_summaries(chunks, profile["chapter_map"], kb_name)
        ids = [c.chunk_id for c in summaries]
        try:
            vs.collection.delete(ids=ids)
        except Exception:  # noqa: BLE001
            pass
        vs.add(ids=ids, texts=[c.text for c in summaries],
               metadatas=[c.metadata() for c in summaries])
        logger.info("Refreshed %d summaries for %s.", len(summaries), kb_name)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true",
                    help="wipe and rebuild even if store is populated")
    ap.add_argument("--refresh-summaries", action="store_true")
    args = ap.parse_args()

    if args.refresh_summaries:
        return refresh_summaries_only()

    books = _available_books()
    if not books:
        logger.error("No structured JSON found. Run scripts/ingest_book.py "
                     "and/or scripts/ingest_pmbok.py first.")
        return 2

    vs = VectorStore()
    existing = vs.count()
    if existing > 0 and not args.rebuild:
        logger.info("Vector store already populated (%d chunks). Pass --rebuild "
                    "to force.", existing)
        return 0
    if args.rebuild:
        logger.info("--rebuild: resetting collection.")
        vs.reset()

    logger.info("Building from %d book(s): %s", len(books),
                ", ".join(kb for kb, _ in books))
    all_chunks: list[Chunk] = []
    parent_store: dict[str, str] = {}
    for kb_name, json_path in books:
        chunks, parents = _chunk_book(kb_name, json_path)
        all_chunks.extend(chunks)
        parent_store.update(parents)

    logger.info("Embedding + loading %d chunks into Chroma ...", len(all_chunks))
    vs.add(ids=[c.chunk_id for c in all_chunks],
           texts=[c.text for c in all_chunks],
           metadatas=[c.metadata() for c in all_chunks])

    logger.info("Building combined BM25 index ...")
    bm = BM25Index()
    bm.build([c.chunk_id for c in all_chunks],
             [c.text for c in all_chunks],
             [c.metadata() for c in all_chunks])
    bm.save()

    config.PARENT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with config.PARENT_STORE_PATH.open("w", encoding="utf-8") as f:
        json.dump(parent_store, f, ensure_ascii=False)

    # per-book counts for visibility
    from collections import Counter
    counts = Counter(c.knowledge_base for c in all_chunks)
    logger.info("Phase 2 complete: %d chunks in Chroma %s; BM25 + parent store "
                "(%d sections) built.", vs.count(), dict(counts), len(parent_store))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
