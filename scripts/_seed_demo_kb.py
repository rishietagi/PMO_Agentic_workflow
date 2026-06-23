"""Seed a realistic SYNTHETIC knowledge base into the real store paths so the
app is fully testable before the (slow) real RITA OCR completes.

This is a PLACEHOLDER: chunks are hand-written PM best-practice summaries with
synthetic page numbers, tagged knowledge_base="DEMO_synthetic". The background
finisher rebuilds the store from the real book (build_vector_store --rebuild),
which overwrites this. Run: python scripts/_seed_demo_kb.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from pmo_engine import config  # noqa: E402
from pmo_engine.retrieval.bm25_index import BM25Index  # noqa: E402
from pmo_engine.retrieval.vector_store import VectorStore  # noqa: E402

# (knowledge_area, chapter, section, content_type, page, text)
CHUNKS = [
    ("Integration", 4, "Develop Project Charter", "concept", 109,
     "The project charter formally authorizes the project and the project "
     "manager. Inputs include the business case, agreements, and enterprise "
     "environmental factors. The charter documents high-level requirements, "
     "objectives, success criteria, a summary milestone schedule, and the "
     "assigned sponsor and stakeholders."),
    ("Integration", 4, "Perform Integrated Change Control", "concept", 137,
     "Integrated change control evaluates all change requests through a change "
     "control board (CCB). Every change must be assessed for impact on scope, "
     "schedule, cost, quality, and risk before approval, and updated baselines "
     "and the change log must be maintained. Projects need a formal closure "
     "process capturing lessons learned."),
    ("Scope", 5, "Create WBS", "concept", 152,
     "Scope management requires collecting requirements, defining scope, and "
     "creating a work breakdown structure (WBS) that decomposes deliverables "
     "into manageable work packages. The scope baseline comprises the scope "
     "statement, the WBS, and the WBS dictionary. A requirements traceability "
     "matrix links requirements to deliverables."),
    ("Scope", 5, "Validate and Control Scope", "concept", 168,
     "Validate Scope formalizes acceptance of completed deliverables with the "
     "customer. Control Scope monitors the status of scope and manages changes "
     "to the scope baseline, preventing scope creep and gold plating."),
    ("Schedule", 6, "Develop Schedule", "concept", 195,
     "Schedule management sequences activities, estimates durations, and "
     "develops a schedule using the critical path method. A schedule baseline "
     "and clearly defined milestones are required. Techniques include critical "
     "path, resource leveling, and schedule compression (crashing, fast "
     "tracking)."),
    ("Cost", 7, "Determine Budget", "concept", 232,
     "Cost management estimates activity costs and aggregates them into a cost "
     "baseline (the time-phased budget). A management reserve is held for "
     "unknown risks. Earned value management measures performance."),
    ("Cost", 7, "Earned Value Formulas", "formula", 240,
     "Earned value: CPI = EV / AC and SPI = EV / PV. Cost variance CV = EV - "
     "AC; schedule variance SV = EV - PV. Estimate at completion EAC = BAC / "
     "CPI when variances are typical. A CPI below 1.0 indicates a cost "
     "overrun."),
    ("Quality", 8, "Manage and Control Quality", "concept", 268,
     "Quality management plans measurable quality metrics, performs quality "
     "assurance to audit processes, and performs quality control to inspect "
     "deliverables against acceptance criteria. The cost of quality includes "
     "prevention, appraisal, and failure costs."),
    ("Resources", 9, "Develop and Manage Team", "concept", 305,
     "Resource management plans, acquires, develops, and manages the team and "
     "physical resources. A RACI (responsibility assignment matrix) clarifies "
     "roles. Team development uses the Tuckman stages: forming, storming, "
     "norming, performing, adjourning."),
    ("Communications", 10, "Plan Communications Management", "concept", 340,
     "A communications management plan defines what information is distributed "
     "to which stakeholders, how frequently, and through which channels. The "
     "number of communication channels is n(n-1)/2 for n stakeholders."),
    ("Risk", 11, "Plan Risk Responses", "concept", 372,
     "Risk management maintains a risk register containing identified risks, "
     "their causes, qualitative and quantitative analysis, risk owners, and "
     "planned responses. Threat strategies: escalate, avoid, transfer, "
     "mitigate, accept. Opportunity strategies: escalate, exploit, share, "
     "enhance, accept. A risk report summarizes overall project risk."),
    ("Risk", 11, "Identify Risks", "concept", 360,
     "Risks should be identified continuously using techniques such as "
     "brainstorming, checklists, assumption analysis, and SWOT. Each risk is "
     "recorded in the risk register with a probability and impact assessment."),
    ("Procurement", 12, "Plan Procurement Management", "concept", 420,
     "Procurement management selects contract types based on risk allocation: "
     "fixed-price (FFP, FPIF), cost-reimbursable (CPFF, CPIF, CPAF), and time "
     "and materials. Make-or-buy analysis and a procurement statement of work "
     "are key inputs."),
    ("Stakeholders", 13, "Identify and Engage Stakeholders", "concept", 460,
     "Stakeholder management builds a stakeholder register and a stakeholder "
     "engagement assessment matrix mapping current vs. desired engagement "
     "(unaware, resistant, neutral, supportive, leading). Engagement is "
     "planned and monitored throughout the project."),
    ("exam_meta", 14, "Common Project Management Errors and Pitfalls",
     "common_pitfall", 502,
     "Common project management errors and pitfalls: not creating a real WBS, "
     "skipping or maintaining a stale risk register, weak or absent integrated "
     "change control, gold plating, vague requirements, ignoring stakeholder "
     "engagement, unrealistic schedules with no baseline, and failing to "
     "perform formal project closure and capture lessons learned."),
    ("exam_meta", 1, "Tricks of the Trade", "exam_tip", 12,
     "PMI mindset: the project manager plans before doing, manages proactively "
     "rather than reactively, addresses root causes, and follows the project "
     "management plan. Changes go through integrated change control."),
]


def main() -> int:
    vs = VectorStore()
    vs.reset()
    ids, texts, metas, parents = [], [], [], {}
    for i, (ka, ch, sec, ct, page, text) in enumerate(CHUNKS):
        cid = f"demo{i:03d}"
        sp = f"Ch.{ch} {ka} > {sec}"
        meta = {
            "chapter_number": ch,
            "chapter_title": config.CHAPTER_MAP.get(ch, {}).get("title", ka),
            "knowledge_area": ka, "section_path": sp,
            "page_start": page, "page_end": page, "content_type": ct,
            "process_group": "Planning",
            "knowledge_base": "DEMO_synthetic", "summary_method": "",
        }
        ids.append(cid); texts.append(text); metas.append(meta); parents[sp] = text
    vs.add(ids, texts, metas)
    bm = BM25Index(); bm.build(ids, texts, metas); bm.save()
    config.PARENT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with config.PARENT_STORE_PATH.open("w", encoding="utf-8") as f:
        json.dump(parents, f, ensure_ascii=False)
    logging.info("Seeded DEMO knowledge base: %d chunks into %s",
                 vs.count(), config.CHROMA_DIR)
    logging.info("NOTE: synthetic placeholder — the finisher will overwrite "
                 "this with the real RITA content (build_vector_store --rebuild).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
