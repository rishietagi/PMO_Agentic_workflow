"""Integration smoke test: full agent pipeline on a tiny synthetic KB.

Validates router (real LLM calls) + all 6 agents + LangGraph + citation
grounding + serialization WITHOUT waiting on the full 551-page book OCR. Builds
a small synthetic Chroma store in a temp dir so nothing touches data/chroma_db.
Run: python scripts/_smoke_pipeline.py
"""
from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from pmo_engine import config  # noqa: E402
from pmo_engine.retrieval.bm25_index import BM25Index  # noqa: E402
from pmo_engine.retrieval.hybrid_retriever import HybridRetriever  # noqa: E402
from pmo_engine.retrieval.vector_store import VectorStore  # noqa: E402

# A handful of synthetic "RITA-like" chunks, one+ per knowledge area.
SYN = [
    ("Scope", 5, "Create WBS", "The work breakdown structure decomposes "
     "deliverables into work packages. Requirements must be collected and a "
     "scope baseline (scope statement, WBS, WBS dictionary) established. "
     "Validate Scope formalizes acceptance; Control Scope manages scope creep."),
    ("Schedule", 6, "Develop Schedule", "Sequence activities, estimate "
     "durations, and develop the schedule using critical path method. A "
     "schedule baseline and milestones are required."),
    ("Cost", 7, "Determine Budget", "Estimate costs and aggregate into a cost "
     "baseline. Earned value management uses CPI=EV/AC and SPI=EV/PV to measure "
     "performance; EAC forecasts final cost."),
    ("Quality", 8, "Manage Quality", "Plan quality with measurable metrics. "
     "Quality assurance audits processes; quality control inspects "
     "deliverables against acceptance criteria."),
    ("Resources", 9, "Develop Team", "Acquire, develop, and manage the team. A "
     "responsibility assignment matrix (RACI) clarifies roles."),
    ("Communications", 10, "Plan Communications", "A communications management "
     "plan defines what information goes to which stakeholders, how often, and "
     "through which channel."),
    ("Risk", 11, "Plan Risk Responses", "Maintain a risk register with "
     "identified risks, qualitative/quantitative analysis, and response "
     "strategies: avoid, transfer, mitigate, accept for threats; exploit, "
     "share, enhance, accept for opportunities."),
    ("Procurement", 12, "Plan Procurement", "Select contract types (fixed "
     "price, cost reimbursable, time and materials) based on risk allocation."),
    ("Stakeholders", 13, "Identify Stakeholders", "Build a stakeholder register "
     "and a stakeholder engagement assessment matrix; plan engagement."),
    ("Integration", 4, "Develop Project Charter", "The project charter "
     "authorizes the project. Develop the project management plan, direct and "
     "manage work, and perform integrated change control via a change control "
     "board. Close the project or phase formally."),
    ("exam_meta", 14, "Common Pitfalls", "Common project management errors: "
     "skipping the WBS, no risk register, gold plating, weak change control, "
     "ignoring stakeholders, and no formal closure."),
]

SOW = ("Migrate our on-prem CRM to a cloud SaaS for 400 users across 3 regions "
       "in 9 months on a $1.2M budget. Integrate with ERP. No data loss. "
       "Decommission the legacy system.")


def build_temp_retriever(tmp: Path) -> HybridRetriever:
    vs = VectorStore(persist_dir=str(tmp / "chroma"), collection="syn")
    vs.reset()
    ids, texts, metas, parents = [], [], [], {}
    for i, (ka, ch, sec, text) in enumerate(SYN):
        cid = f"s{i:03d}"
        sp = f"Ch.{ch} {ka} > {sec}"
        ct = "common_pitfall" if ka == "exam_meta" else "concept"
        meta = {"chapter_number": ch, "chapter_title": ka, "knowledge_area": ka,
                "section_path": sp, "page_start": 100 + i, "page_end": 100 + i,
                "content_type": ct, "process_group": "Planning",
                "knowledge_base": "RITA_10th_Edition", "summary_method": ""}
        ids.append(cid); texts.append(text); metas.append(meta)
        parents[sp] = text
    vs.add(ids, texts, metas)
    bm = BM25Index(); bm.build(ids, texts, metas)
    return HybridRetriever(vector_store=vs, bm25=bm, parent_store=parents)


def main() -> int:
    if not (config.groq_key_present() or config.google_key_present()):
        print("NO API KEY — set GROQ_API_KEY in .env to run this smoke test.")
        return 2
    from pmo_engine.agents.graph import PMOEngine

    # ignore_cleanup_errors: Chroma holds a file handle on Windows at teardown
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        retriever = build_temp_retriever(Path(td))
        engine = PMOEngine(retriever=retriever,
                           second_opinion=config.google_key_present(),
                           max_iterations=1)
        # single run (also exercises the graph); avoids doubling API calls
        state = engine.run(SOW)

    rep = state.validation_report
    opt = state.optimized_plan
    print("\n=== RESULT ===")
    print("project:", state.project_input.title if state.project_input else "?")
    print("draft sections:", len(state.draft_plan.sections) if state.draft_plan else 0)
    print("overall compliance:", rep.overall_compliance_score if rep else "?")
    print("findings:", len(rep.findings) if rep else 0,
          "| gaps:", len(rep.gaps()) if rep else 0,
          "| risk flags:", len(rep.risk_flags()) if rep else 0)
    print("risk/gap items:", len(state.risk_gap_list.items) if state.risk_gap_list else 0)
    print("recommendations:", len(state.recommendations.items) if state.recommendations else 0)
    print("optimized compliance:", opt.compliance_score if opt else "?")
    if rep and rep.second_opinion:
        print("2nd opinion:", rep.second_opinion[:120])
    # show a couple of grounded citations
    cited = [f for f in (rep.findings if rep else []) if f.citations]
    print("\nsample cited findings:")
    for f in cited[:3]:
        print(f"  [{f.finding_type}/{f.severity}] {f.knowledge_area}: "
              f"{f.statement[:70]}")
        for c in f.citations[:2]:
            print("     ->", c.display())
    # serialization sanity (what the FastAPI layer sends)
    json.loads(state.model_dump_json())
    print("\nserialization OK. SMOKE TEST PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
