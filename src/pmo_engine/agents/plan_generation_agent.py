"""Agent 2 — Plan Generation (Step 2: AI Plan Generation).

Generates a DraftPlan: approach, WBS, milestones, and one section per relevant
PMI knowledge area. Reasoning-heavy -> REASONING tier (70B). The per-area
sections are deliberately structured so the Validation Agent can map each one
to a knowledge_area retrieval filter.
"""
from __future__ import annotations

import logging

from pmo_engine import config
from pmo_engine.agents.state import DraftPlan, PlanSection, ProjectInput
from pmo_engine.llm.router import LLMRouter, TaskTier, get_router

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a senior project manager generating an initial project management "
    "plan aligned to PMI knowledge areas. Produce a concrete, actionable draft "
    "grounded in the provided project input. Return ONLY JSON with keys: "
    "project_title, approach, wbs[] (5-10 work-package strings), milestones[] "
    "(4-8 strings), sections[] where each section is "
    "{knowledge_area, title, content, key_elements[]}. "
    "Generate one section for EACH of these knowledge areas: "
    + ", ".join(config.PLAN_KNOWLEDGE_AREAS) + ". "
    "Keep each section's content 4-8 sentences, specific to this project.")


class PlanGenerationAgent:
    def __init__(self, router: LLMRouter | None = None) -> None:
        self.router = router or get_router()

    def run(self, project: ProjectInput) -> DraftPlan:
        logger.info("PlanGen: drafting plan across %d knowledge areas.",
                    len(config.PLAN_KNOWLEDGE_AREAS))
        user = (
            f"Project title: {project.title}\n"
            f"Summary: {project.summary}\n"
            f"Objectives: {project.objectives}\n"
            f"Scope: {project.scope}\n"
            f"Deliverables: {project.deliverables}\n"
            f"Requirements: {project.requirements}\n"
            f"Constraints: {project.constraints}\n"
            f"Stakeholders: {project.stakeholders}\n"
            f"Timeline: {project.timeline}\nBudget: {project.budget}\n")
        data = self.router.complete_json(_SYSTEM, user, tier=TaskTier.REASONING,
                                         max_tokens=4000)
        plan = self._coerce(data, project)
        # guarantee one section per knowledge area for downstream validation
        present = {s.knowledge_area for s in plan.sections}
        for ka in config.PLAN_KNOWLEDGE_AREAS:
            if ka not in present:
                plan.sections.append(PlanSection(
                    knowledge_area=ka, title=f"{ka} Management",
                    content="(Not addressed in the draft plan.)"))
        return plan

    @staticmethod
    def _coerce(data: dict, project: ProjectInput) -> DraftPlan:
        if not data:
            return DraftPlan(project_title=project.title)
        sections = []
        for s in data.get("sections", []) or []:
            if not isinstance(s, dict):
                continue
            ke = s.get("key_elements", [])
            if isinstance(ke, str):
                ke = [ke]
            sections.append(PlanSection(
                knowledge_area=s.get("knowledge_area", "") or s.get("title", ""),
                title=s.get("title", ""), content=s.get("content", ""),
                key_elements=ke or []))
        return DraftPlan(
            project_title=data.get("project_title", project.title),
            approach=data.get("approach", ""),
            wbs=_as_list(data.get("wbs")),
            milestones=_as_list(data.get("milestones")),
            sections=sections)


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str) and v:
        return [v]
    return []
