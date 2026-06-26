"""Agent 4 — Gap & Risk Identification (Step 4).

Consolidates the Validation Agent's gaps/risk flags into a severity-ranked
RiskGapList, and enriches it by cross-referencing the Risk chapter (Ch.11) and
the 'Common Project Management Errors and Pitfalls' content (Ch.14) — exactly
the curated 'what PMI flags as mistakes' material this agent should check
against (the design spec). Citations carried through.
"""
from __future__ import annotations

import logging

from pmo_engine.agents.state import (Citation, DraftPlan, RiskGapItem,
                                     RiskGapList, ValidationReport)
from pmo_engine.llm.router import LLMRouter, TaskTier, get_router
from pmo_engine.retrieval.hybrid_retriever import HybridRetriever

logger = logging.getLogger(__name__)

_SYS = (
    "You are a PMO risk analyst. Given a draft plan summary, the validation "
    "gaps/risk flags already found, and reference excerpts on risk management "
    "and common PM pitfalls, produce a consolidated, de-duplicated list of "
    "gaps and risks. For each, assess severity, likelihood, impact, and a "
    "concrete mitigation. Cite supporting excerpts by id.\n"
    "Return ONLY JSON: {\"items\": [{\"category\": \"gap|risk\", "
    "\"knowledge_area\": \"...\", \"title\": \"...\", \"description\": \"...\", "
    "\"severity\": \"low|medium|high\", \"likelihood\": \"...\", "
    "\"impact\": \"...\", \"mitigation\": \"...\", \"source_ids\": [\"E1\"]}]}")


class GapRiskAgent:
    def __init__(self, router: LLMRouter | None = None,
                 retriever: HybridRetriever | None = None) -> None:
        self.router = router or get_router()
        self.retriever = retriever or HybridRetriever()

    def run(self, plan: DraftPlan, report: ValidationReport) -> RiskGapList:
        logger.info("Gap&Risk: consolidating + cross-referencing Ch.11/Ch.14.")
        # Pull pitfall + risk-management evidence directly.
        pitfalls = self.retriever.retrieve(
            "common project management errors and pitfalls to avoid",
            content_types=["common_pitfall", "exam_tip"], top_k=4)
        risk_ref = self.retriever.retrieve(
            "risk response strategies risk register qualitative quantitative "
            "analysis", knowledge_area="Risk", top_k=4)
        evidence_chunks = (pitfalls + risk_ref)[:8]
        id_map = {}
        ev_lines = []
        for i, rc in enumerate(evidence_chunks, 1):
            eid = f"E{i}"
            id_map[eid] = rc
            ev_lines.append(f"[{eid}] ({rc.citation()})\n{rc.text[:600]}")
        evidence = "\n\n".join(ev_lines) or "(none)"

        existing = []
        for f in report.gaps() + report.risk_flags():
            existing.append(f"- ({f.finding_type}/{f.severity}) "
                            f"[{f.knowledge_area}] {f.statement}")
        existing_block = "\n".join(existing) or "(none flagged yet)"

        user = (f"Project: {plan.project_title}\n"
                f"Overall compliance score: {report.overall_compliance_score}\n\n"
                f"--- VALIDATION GAPS & RISK FLAGS ---\n{existing_block}\n\n"
                f"--- REFERENCE EXCERPTS (risk mgmt + common pitfalls) ---\n"
                f"{evidence}\n")
        data = self.router.complete_json(_SYS, user, tier=TaskTier.REASONING,
                                         max_tokens=3000)

        items: list[RiskGapItem] = []
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
            items.append(RiskGapItem(
                category=it.get("category", "risk"),
                knowledge_area=it.get("knowledge_area", ""),
                title=it.get("title", ""),
                description=it.get("description", ""),
                severity=it.get("severity", "medium"),
                likelihood=it.get("likelihood", ""),
                impact=it.get("impact", ""),
                mitigation=it.get("mitigation", ""),
                citations=cits))

        # Safety net: if the LLM returned nothing, lift validation findings.
        if not items:
            for f in report.gaps() + report.risk_flags():
                items.append(RiskGapItem(
                    category="gap" if f.finding_type == "gap" else "risk",
                    knowledge_area=f.knowledge_area, title=f.statement[:80],
                    description=f.statement, severity=f.severity,
                    mitigation="", citations=f.citations))
        logger.info("Gap&Risk: %d consolidated items.", len(items))
        return RiskGapList(items=items)
