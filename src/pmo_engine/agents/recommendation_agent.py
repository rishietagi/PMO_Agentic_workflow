"""Agent 5 — AI Recommendations (Step 5).

Turns gaps/risks + validation findings into concrete, prioritized,
RAG-grounded recommendations. Each recommendation cites a chapter/page so a
PMO manager can trace it (the design spec). Reasoning tier.
"""
from __future__ import annotations

import logging

from pmo_engine.agents.state import (Citation, DraftPlan, Recommendation,
                                     Recommendations, RiskGapList,
                                     ValidationReport)
from pmo_engine.llm.router import LLMRouter, TaskTier, get_router
from pmo_engine.retrieval.hybrid_retriever import HybridRetriever

logger = logging.getLogger(__name__)

_SYS = (
    "You are a PMO advisor. Produce concrete, prioritized recommendations that "
    "close the identified gaps and mitigate the risks, each grounded in the "
    "supplied PMI reference excerpts and citing them by id. Be specific and "
    "actionable — name the artifact, process, or technique to add/change.\n"
    "Return ONLY JSON: {\"items\": [{\"knowledge_area\": \"...\", "
    "\"recommendation\": \"...\", \"rationale\": \"...\", "
    "\"priority\": \"low|medium|high\", \"addresses\": \"gap/risk it targets\", "
    "\"source_ids\": [\"E1\"]}]}")


class RecommendationAgent:
    def __init__(self, router: LLMRouter | None = None,
                 retriever: HybridRetriever | None = None) -> None:
        self.router = router or get_router()
        self.retriever = retriever or HybridRetriever()

    def run(self, plan: DraftPlan, report: ValidationReport,
            risk_gaps: RiskGapList) -> Recommendations:
        logger.info("Recommendations: grounding fixes for %d gap/risk items.",
                    len(risk_gaps.items))
        # gather evidence per the knowledge areas that have problems
        problem_areas = {i.knowledge_area for i in risk_gaps.items
                         if i.knowledge_area}
        problem_areas |= {f.knowledge_area for f in report.gaps()}
        id_map = {}
        ev_lines = []
        eid_n = 0
        for ka in sorted(a for a in problem_areas if a):
            for rc in self.retriever.retrieve(
                    f"best practices required elements for {ka} management",
                    knowledge_area=ka, top_k=2):
                eid_n += 1
                eid = f"E{eid_n}"
                id_map[eid] = rc
                ev_lines.append(f"[{eid}] ({rc.citation()})\n{rc.text[:500]}")
        evidence = "\n\n".join(ev_lines) or "(no excerpts)"

        items_block = "\n".join(
            f"- [{i.category}/{i.severity}] ({i.knowledge_area}) {i.title}: "
            f"{i.description}" for i in risk_gaps.ranked()) or "(none)"

        user = (f"Project: {plan.project_title}\n"
                f"Compliance score: {report.overall_compliance_score}\n\n"
                f"--- GAPS & RISKS ---\n{items_block}\n\n"
                f"--- REFERENCE EXCERPTS ---\n{evidence}\n")
        data = self.router.complete_json(_SYS, user, tier=TaskTier.REASONING,
                                         max_tokens=3000)

        items: list[Recommendation] = []
        for it in (data.get("items", []) if isinstance(data, dict) else []):
            if not isinstance(it, dict):
                continue
            cits = []
            for sid in it.get("source_ids", []) or []:
                rc = id_map.get(str(sid))
                if rc:
                    m = rc.metadata
                    cits.append(Citation(
                        chapter_number=int(m.get("chapter_number") or 0),
                        chapter_title=m.get("chapter_title", ""),
                        section_path=m.get("section_path", ""),
                        page_start=int(m.get("page_start") or 0),
                        page_end=int(m.get("page_end") or 0),
                        knowledge_base=m.get("knowledge_base", "")))
            items.append(Recommendation(
                knowledge_area=it.get("knowledge_area", ""),
                recommendation=it.get("recommendation", ""),
                rationale=it.get("rationale", ""),
                priority=it.get("priority", "medium"),
                addresses=it.get("addresses", ""),
                citations=cits))
        logger.info("Recommendations: produced %d items.", len(items))
        return Recommendations(items=items)
