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


# --- Detailed eval: chapter + keyword-presence, with MRR (no LLM) -----------
@dataclass
class DetailedCase:
    query: str
    expected_chapter: int
    knowledge_area: str
    keywords: list[str]  # any appearing in a top-k chunk = a content hit


DETAILED_CASES: list[DetailedCase] = [
    DetailedCase("What are the inputs to Develop Project Charter?", 4, "Integration", ["business case", "agreement", "charter"]),
    DetailedCase("How does the change control board handle change requests?", 4, "Integration", ["change control board", "change request"]),
    DetailedCase("How is project work directed and managed to produce deliverables?", 4, "Integration", ["deliverable", "work performance"]),
    DetailedCase("How do you collect requirements and trace them?", 5, "Scope", ["requirement", "traceability"]),
    DetailedCase("How is a work breakdown structure decomposed into work packages?", 5, "Scope", ["work breakdown", "decompos", "work package"]),
    DetailedCase("What is the difference between Validate Scope and Control Scope?", 5, "Scope", ["validate scope", "control scope", "accept"]),
    DetailedCase("How do you develop the schedule using critical path method?", 6, "Schedule", ["critical path", "schedule"]),
    DetailedCase("How are activity durations estimated?", 6, "Schedule", ["duration", "estimat"]),
    DetailedCase("How is the cost baseline and budget determined?", 7, "Cost", ["cost baseline", "budget"]),
    DetailedCase("What earned value metrics forecast cost at completion?", 7, "Cost", ["earned value", "estimate at completion", "forecast"]),
    DetailedCase("How do you manage and control quality?", 8, "Quality", ["quality", "control quality"]),
    DetailedCase("How is the project team acquired and developed?", 9, "Resources", ["team", "resource"]),
    DetailedCase("What goes into a communications management plan?", 10, "Communications", ["communications management plan", "information"]),
    DetailedCase("List the risk response strategies for threats and opportunities.", 11, "Risk", ["avoid", "transfer", "mitigate", "exploit", "enhance"]),
    DetailedCase("What does a risk register contain?", 11, "Risk", ["risk register"]),
    DetailedCase("How do qualitative and quantitative risk analysis differ?", 11, "Risk", ["qualitative", "quantitative", "probability"]),
    DetailedCase("What contract types are used in procurement?", 12, "Procurement", ["fixed-price", "cost-reimbursable", "time and material"]),
    DetailedCase("What is in a stakeholder register?", 13, "Stakeholders", ["stakeholder register"]),
    DetailedCase("How does the stakeholder engagement assessment matrix work?", 13, "Stakeholders", ["engagement", "unaware", "resistant", "supportive"]),
    DetailedCase("How are procurement make-or-buy decisions documented?", 12, "Procurement", ["make-or-buy", "procurement"]),
    # --- harder / indirectly-worded queries (real headroom) ---
    DetailedCase("How do we keep the project from going over budget once work starts?", 7, "Cost", ["control cost", "cost baseline", "variance"]),
    DetailedCase("What stops the agreed deliverables from being changed without approval?", 4, "Integration", ["change control", "change request"]),
    DetailedCase("How do we get the customer to formally sign off on what we built?", 5, "Scope", ["validate scope", "accept"]),
    DetailedCase("What technique combines optimistic, most likely and pessimistic estimates?", 6, "Schedule", ["three-point", "pert", "optimistic"]),
    DetailedCase("How do we put a dollar figure on overall project risk?", 11, "Risk", ["quantitative", "monte carlo", "expected monetary"]),
    DetailedCase("How do we stop the scope from quietly expanding over time?", 5, "Scope", ["scope creep", "control scope"]),
    DetailedCase("How do we measure whether the project is ahead of or behind plan?", 7, "Cost", ["earned value", "schedule variance", "spi"]),
    DetailedCase("How should we tailor engagement for resistant stakeholders?", 13, "Stakeholders", ["engagement", "resistant", "manage stakeholder"]),
]


def detailed_run(top_n: int = 5, use_filter: bool = True) -> dict:
    retriever = HybridRetriever()
    available = _available_chapters()
    cases = [c for c in DETAILED_CASES if not available or c.expected_chapter in available]
    ch_hits = mrr_sum = kw_hits = 0
    logger.info("Detailed eval over %d cases (top-%d, KA-filter=%s): "
                "chapter@%d, MRR@10, keyword-hit@%d\n", len(cases), top_n,
                use_filter, top_n, top_n)
    kw_at1 = kw_mrr_sum = 0
    for c in cases:
        ka = c.knowledge_area if use_filter else None
        results = retriever.retrieve(c.query, knowledge_area=ka,
                                     top_k=10, expand_parent=False)
        chapters = [r.metadata.get("chapter_number") for r in results]
        ch_ok = c.expected_chapter in chapters[:top_n]
        rr = next((1.0/(i+1) for i, ch in enumerate(chapters)
                   if ch == c.expected_chapter), 0.0)
        # passage-level: rank of first chunk whose TEXT contains an answer term
        kws = [k.lower() for k in c.keywords]
        kw_rank = next((i for i, r in enumerate(results)
                        if any(k in r.text.lower() for k in kws)), None)
        kw_ok5 = kw_rank is not None and kw_rank < top_n
        kw_ok1 = kw_rank == 0
        kw_mrr = 1.0/(kw_rank+1) if kw_rank is not None else 0.0
        ch_hits += ch_ok; mrr_sum += rr; kw_hits += kw_ok5
        kw_at1 += kw_ok1; kw_mrr_sum += kw_mrr
        logger.info("  ch%-2d %s | chMRR=%.2f kwMRR=%.2f kw@1=%s | %s",
                    c.expected_chapter, "OK " if ch_ok else "MISS", rr, kw_mrr,
                    "Y" if kw_ok1 else "n", c.query[:42])
    n = len(cases) or 1
    out = {"n": len(cases), "chapter_hit": ch_hits/n, "mrr": mrr_sum/n,
           "keyword_hit5": kw_hits/n, "keyword_at1": kw_at1/n,
           "keyword_mrr": kw_mrr_sum/n}
    logger.info("\n=== DETAILED (filter=%s): chapter@%d=%.0f%% | chMRR=%.3f | "
                "kw-hit@%d=%.0f%% | kw-hit@1=%.0f%% | kw-MRR=%.3f (n=%d) ===",
                use_filter, top_n, out["chapter_hit"]*100, out["mrr"], top_n,
                out["keyword_hit5"]*100, out["keyword_at1"]*100,
                out["keyword_mrr"], out["n"])
    return out


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
    ap.add_argument("--detailed", action="store_true",
                    help="MRR@10 + keyword-hit@5 metrics (sensitive to chunking)")
    args = ap.parse_args()
    from pmo_engine.retrieval.vector_store import VectorStore
    if VectorStore().count() == 0:
        logger.error("Vector store empty — build it first "
                     "(scripts/build_vector_store.py).")
        return 2
    if args.detailed:
        detailed_run(top_n=5, use_filter=not args.no_filter)
    else:
        run(top_n=args.top_n, use_filter=not args.no_filter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
