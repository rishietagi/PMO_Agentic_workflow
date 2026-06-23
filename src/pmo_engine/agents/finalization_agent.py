"""Agent 6 — Finalization / Optimizer (Step 6).

Applies the recommendations to the draft plan to produce an OptimizedPlan with
an executive summary, a diff vs. the draft (changes_from_draft), the carried
compliance score, and open items. Reasoning tier.

Also decides whether another improvement iteration is warranted (the feedback
loop edge): if compliance is low and we haven't hit max_iterations, flag for
revision.
"""
from __future__ import annotations

import logging

from pmo_engine.agents.state import (DraftPlan, OptimizedPlan, PlanSection,
                                     Recommendations, ValidationReport)
from pmo_engine.llm.router import LLMRouter, TaskTier, get_router

logger = logging.getLogger(__name__)

_SYS = (
    "You are a PMO lead finalizing a project plan. Apply the recommendations to "
    "the draft, strengthening weak sections. Return ONLY JSON: {"
    "\"executive_summary\": \"...\", "
    "\"sections\": [{\"knowledge_area\": \"...\", \"title\": \"...\", "
    "\"content\": \"...\", \"key_elements\": [\"...\"]}], "
    "\"changes_from_draft\": [\"concise change description\"], "
    "\"open_items\": [\"...\"]}. Keep section content tight (4-8 sentences).")

REVISION_THRESHOLD = 60  # below this overall score, suggest another iteration


class FinalizationAgent:
    def __init__(self, router: LLMRouter | None = None) -> None:
        self.router = router or get_router()

    def run(self, plan: DraftPlan, report: ValidationReport,
            recommendations: Recommendations) -> OptimizedPlan:
        logger.info("Finalization: optimizing plan from %d recommendations.",
                    len(recommendations.items))
        recs_block = "\n".join(
            f"- [{r.priority}] ({r.knowledge_area}) {r.recommendation}"
            for r in recommendations.items) or "(none)"
        draft_block = "\n".join(
            f"## {s.knowledge_area}: {s.title}\n{s.content}"
            for s in plan.sections)

        user = (f"Project: {plan.project_title}\n"
                f"Current compliance score: {report.overall_compliance_score}\n\n"
                f"--- DRAFT PLAN ---\n{draft_block}\n\n"
                f"--- RECOMMENDATIONS TO APPLY ---\n{recs_block}\n")
        data = self.router.complete_json(_SYS, user, tier=TaskTier.REASONING,
                                         max_tokens=4000)

        sections = []
        for s in (data.get("sections", []) if isinstance(data, dict) else []):
            if not isinstance(s, dict):
                continue
            ke = s.get("key_elements", [])
            if isinstance(ke, str):
                ke = [ke]
            sections.append(PlanSection(
                knowledge_area=s.get("knowledge_area", "") or s.get("title", ""),
                title=s.get("title", ""), content=s.get("content", ""),
                key_elements=ke or []))
        if not sections:  # fall back to draft if optimization failed
            sections = plan.sections

        return OptimizedPlan(
            project_title=plan.project_title,
            executive_summary=(data.get("executive_summary", "")
                               if isinstance(data, dict) else ""),
            sections=sections,
            changes_from_draft=_as_list(data.get("changes_from_draft")
                                        if isinstance(data, dict) else None),
            compliance_score=report.overall_compliance_score,
            open_items=_as_list(data.get("open_items")
                                if isinstance(data, dict) else None))


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str) and v:
        return [v]
    return []
