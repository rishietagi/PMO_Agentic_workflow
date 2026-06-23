"""Phase 3 — Retrieval sanity-check harness (CLAUDE.md §6.8).

A fixed set of test queries with a known-correct expected chapter. Asserts the
expected chapter appears in the top-3 reranked results. Pure retrieval — no LLM
API needed, so it runs without API keys. Reports a pass rate; if it's well
under ~70% that's a loud signal that chunking/embedding needs tuning before the
agents can be trusted.

    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --top-n 3
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pmo_engine import config  # noqa: E402
from pmo_engine.retrieval.hybrid_retriever import HybridRetriever  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("eval_retrieval")


@dataclass
class TestCase:
    query: str
    expected_chapter: int
    knowledge_area: str | None = None  # if set, exercise the pre-filter too


# Known-correct answers grounded in the Section 1 chapter map.
TEST_CASES: list[TestCase] = [
    TestCase("What are the inputs to Develop Project Charter?", 4, "Integration"),
    TestCase("How do you perform integrated change control?", 4, "Integration"),
    TestCase("What is a work breakdown structure and how is it decomposed?", 5, "Scope"),
    TestCase("How do you validate and control project scope?", 5, "Scope"),
    TestCase("What techniques are used to develop the project schedule?", 6, "Schedule"),
    TestCase("How is critical path calculated in a network diagram?", 6, "Schedule"),
    TestCase("What are the earned value management formulas (CPI, SPI, EAC)?", 7, "Cost"),
    TestCase("How do you determine the project budget and cost baseline?", 7, "Cost"),
    TestCase("What is the difference between quality assurance and quality control?", 8, "Quality"),
    TestCase("How do you build and develop a project team?", 9, "Resources"),
    TestCase("What goes into a communications management plan?", 10, "Communications"),
    TestCase("List the risk response strategies for threats and opportunities.", 11, "Risk"),
    TestCase("What does a risk register contain?", 11, "Risk"),
    TestCase("What are the contract types used in procurement?", 12, "Procurement"),
    TestCase("What is in a stakeholder register and engagement assessment matrix?", 13, "Stakeholders"),
    TestCase("What are common project management errors and pitfalls to avoid?", 14, None),
]


def _available_chapters() -> set[int]:
    """Chapters actually present in the store (so we only test loaded books)."""
    from pmo_engine.retrieval.vector_store import VectorStore
    chapters: set[int] = set()
    try:
        data = VectorStore().collection.get(include=["metadatas"])
        for m in data.get("metadatas", []) or []:
            ch = m.get("chapter_number")
            if isinstance(ch, int):
                chapters.add(ch)
    except Exception:  # noqa: BLE001
        pass
    return chapters


def run(top_n: int = 3, use_filter: bool = True) -> float:
    retriever = HybridRetriever()
    available = _available_chapters()
    cases = [tc for tc in TEST_CASES
             if not available or tc.expected_chapter in available]
    skipped = len(TEST_CASES) - len(cases)
    passed = 0
    logger.info("Running %d retrieval test cases (top-%d)%s...\n",
                len(cases), top_n,
                f"; skipped {skipped} for chapters not in the loaded KB"
                if skipped else "")
    for tc in cases:
        ka = tc.knowledge_area if use_filter else None
        results = retriever.retrieve(tc.query, knowledge_area=ka,
                                     top_k=top_n, expand_parent=False)
        chapters = [r.metadata.get("chapter_number") for r in results]
        ok = tc.expected_chapter in chapters
        passed += ok
        flag = "PASS" if ok else "FAIL"
        logger.info("[%s] ch%-2d exp | got %s | %s",
                    flag, tc.expected_chapter, chapters, tc.query[:55])
    rate = passed / len(cases) if cases else 0.0
    logger.info("\n=== Retrieval pass rate: %d/%d = %.0f%% (expected chapter in "
                "top-%d) ===", passed, len(cases), rate * 100, top_n)
    if rate < 0.70:
        logger.warning("!!! Pass rate under 70%% — tune chunking/embedding "
                       "before trusting the agents built on top of retrieval.")
    return rate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--no-filter", action="store_true",
                    help="disable knowledge_area pre-filter (ablation)")
    args = ap.parse_args()
    from pmo_engine.retrieval.vector_store import VectorStore
    if VectorStore().count() == 0:
        logger.error("Vector store empty — build it first "
                     "(scripts/build_vector_store.py).")
        return 2
    run(top_n=args.top_n, use_filter=not args.no_filter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
