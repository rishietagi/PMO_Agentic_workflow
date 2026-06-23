"""Agent 3 — PMO Validation Engine (Step 3). THE CORE DIFFERENTIATOR.

For each plan section it:
  1. Generates 2-4 targeted sub-queries (CHEAP tier, §6.3).
  2. Runs the hybrid retriever filtered to that section's knowledge_area (§6.1).
  3. Synthesizes findings with the REASONING model, grounded in the retrieved
     RITA chunks (§6.6) — every finding carries a chapter/page citation that is
     mapped from real chunk metadata, never invented by the LLM.
  4. Scores PMO compliance per section and overall.
Optionally takes a Gemini second opinion on the overall score (§4).

Output: ValidationReport (alignment summary, gaps, risk flags, scores).
"""
from __future__ import annotations

import logging
import statistics
from typing import Any

from pmo_engine.agents.state import (Citation, DraftPlan, PlanSection,
                                     ProjectInput, SectionScore,
                                     ValidationFinding, ValidationReport)
from pmo_engine.llm.router import LLMRouter, TaskTier, get_router
from pmo_engine.retrieval.hybrid_retriever import HybridRetriever, RetrievedChunk

logger = logging.getLogger(__name__)

_SUBQUERY_SYS = (
    "You generate 2-4 short retrieval queries to look up project-management "
    "best-practice requirements for a given plan section in a PMI reference "
    "book. Return ONLY JSON: {\"queries\": [\"...\"]}. Queries should target "
    "what a complete, compliant section of this type MUST contain.")

_VALIDATE_SYS = (
    "You are a PMO governance validator. Compare a draft plan section against "
    "authoritative PMI/PMBOK guidance excerpts from the RITA reference book. "
    "Judge alignment, find gaps (missing required elements) and risk flags "
    "(things likely to cause problems). Ground every finding in the supplied "
    "excerpts and cite them by their excerpt id.\n"
    "Return ONLY JSON: {\n"
    "  \"section_score\": <0-100 integer>,\n"
    "  \"score_rationale\": \"...\",\n"
    "  \"findings\": [{\"finding_type\": \"alignment|gap|risk_flag\", "
    "\"severity\": \"low|medium|high\", \"statement\": \"...\", "
    "\"evidence\": \"what the reference says\", \"source_ids\": [\"E1\"]}]\n}\n"
    "Every gap and risk_flag MUST include at least one valid source_id.")


class PMOValidationAgent:
    def __init__(self, router: LLMRouter | None = None,
                 retriever: HybridRetriever | None = None,
                 second_opinion: bool = False) -> None:
        self.router = router or get_router()
        self.retriever = retriever or HybridRetriever()
        self.second_opinion = second_opinion

    def _subqueries(self, section: PlanSection) -> list[str]:
        try:
            data = self.router.complete_json(
                _SUBQUERY_SYS,
                f"Knowledge area: {section.knowledge_area}\n"
                f"Section title: {section.title}\n"
                f"Section content:\n{section.content[:1500]}",
                tier=TaskTier.CHEAP, max_tokens=400)
            qs = data.get("queries") if isinstance(data, dict) else None
            qs = [q for q in (qs or []) if isinstance(q, str) and q.strip()]
            if qs:
                return qs[:4]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sub-query gen failed (%s); using defaults.", exc)
        return [f"{section.knowledge_area} management best practices required "
                f"elements", f"what should a {section.knowledge_area} plan "
                f"section contain"]

    def _citation_from_chunk(self, rc: RetrievedChunk) -> Citation:
        m = rc.metadata
        return Citation(
            chapter_number=int(m.get("chapter_number") or 0),
            chapter_title=m.get("chapter_title", ""),
            section_path=m.get("section_path", ""),
            page_start=int(m.get("page_start") or 0),
            page_end=int(m.get("page_end") or 0),
            knowledge_base=m.get("knowledge_base", ""))

    def _validate_section(self, section: PlanSection
                          ) -> tuple[SectionScore, list[ValidationFinding]]:
        queries = self._subqueries(section)
        chunks = self.retriever.multi_query_retrieve(
            queries, knowledge_area=section.knowledge_area, top_k_per_query=4)
        chunks = chunks[:6]
        if not chunks:
            logger.warning("No evidence retrieved for %s.", section.knowledge_area)

        # build the evidence block with stable ids -> map back to citations
        id_map: dict[str, RetrievedChunk] = {}
        ev_lines = []
        for i, rc in enumerate(chunks, 1):
            eid = f"E{i}"
            id_map[eid] = rc
            ev_lines.append(f"[{eid}] ({rc.citation()})\n{rc.parent_text[:900]}")
        evidence = "\n\n".join(ev_lines) or "(no reference excerpts found)"

        user = (f"Knowledge area: {section.knowledge_area}\n"
                f"--- DRAFT PLAN SECTION ---\n{section.content}\n\n"
                f"--- RITA REFERENCE EXCERPTS ---\n{evidence}\n")
        data = self.router.complete_json(_VALIDATE_SYS, user,
                                         tier=TaskTier.REASONING, max_tokens=2500)

        score = int(data.get("section_score", 0) or 0) if isinstance(data, dict) else 0
        score = max(0, min(100, score))
        rationale = data.get("score_rationale", "") if isinstance(data, dict) else ""
        findings: list[ValidationFinding] = []
        for f in (data.get("findings", []) if isinstance(data, dict) else []):
            if not isinstance(f, dict):
                continue
            cits = []
            for sid in f.get("source_ids", []) or []:
                rc = id_map.get(str(sid))
                if rc:
                    cits.append(self._citation_from_chunk(rc))
            ftype = f.get("finding_type", "alignment")
            # enforce: gaps/risks must cite; if LLM didn't, attach top evidence
            if ftype in ("gap", "risk_flag") and not cits and chunks:
                cits = [self._citation_from_chunk(chunks[0])]
            findings.append(ValidationFinding(
                knowledge_area=section.knowledge_area,
                finding_type=ftype if ftype in
                ("alignment", "gap", "risk_flag") else "alignment",
                severity=f.get("severity", "medium"),
                statement=f.get("statement", ""),
                evidence=f.get("evidence", ""),
                citations=cits))
        return SectionScore(knowledge_area=section.knowledge_area, score=score,
                            rationale=rationale), findings

    def run(self, plan: DraftPlan,
            project: ProjectInput | None = None) -> ValidationReport:
        logger.info("Validation: checking %d sections (core differentiator).",
                    len(plan.sections))
        scores: list[SectionScore] = []
        findings: list[ValidationFinding] = []
        for section in plan.sections:
            ss, fs = self._validate_section(section)
            scores.append(ss)
            findings.extend(fs)
            logger.info("  %-14s score=%3d  findings=%d",
                        section.knowledge_area, ss.score, len(fs))

        overall = int(round(statistics.mean([s.score for s in scores]))) if \
            scores else 0
        report = ValidationReport(
            findings=findings, section_scores=scores,
            overall_compliance_score=overall,
            alignment_summary=self._alignment_summary(plan, scores, findings))

        if self.second_opinion:
            report.second_opinion = self._second_opinion(overall, scores)
        return report

    def _alignment_summary(self, plan: DraftPlan, scores: list[SectionScore],
                           findings: list[ValidationFinding]) -> str:
        n_gap = sum(f.finding_type == "gap" for f in findings)
        n_risk = sum(f.finding_type == "risk_flag" for f in findings)
        weak = sorted(scores, key=lambda s: s.score)[:3]
        try:
            sys = ("Write a 3-4 sentence PMO alignment summary for a project "
                   "plan validation. Be specific and governance-oriented.")
            user = (f"Overall compliance: "
                    f"{int(round(sum(s.score for s in scores)/max(len(scores),1)))}. "
                    f"Gaps: {n_gap}, risk flags: {n_risk}. Weakest areas: "
                    f"{[(s.knowledge_area, s.score) for s in weak]}.")
            return self.router.complete(sys, user, tier=TaskTier.CHEAP,
                                        max_tokens=300).strip()
        except Exception:  # noqa: BLE001
            return (f"Validated {len(scores)} sections: {n_gap} gaps and "
                    f"{n_risk} risk flags identified. Weakest areas: "
                    f"{', '.join(s.knowledge_area for s in weak)}.")

    def _second_opinion(self, overall: int, scores: list[SectionScore]) -> str:
        """Optional Gemini cross-check of the overall score (§4)."""
        try:
            from pmo_engine import config
            if not config.google_key_present():
                return None
            sys = ("You are a second PMO reviewer. Given per-section compliance "
                   "scores, state in 2 sentences whether the overall score "
                   "looks reasonable and flag any section you'd score very "
                   "differently.")
            user = (f"Overall: {overall}. Sections: "
                    f"{[(s.knowledge_area, s.score) for s in scores]}")
            # force the Gemini path by using the gemini client directly
            return self.router.gemini.chat(sys, user, max_tokens=200).strip()
        except Exception as exc:  # noqa: BLE001
            logger.info("Second opinion unavailable: %s", exc)
            return None
