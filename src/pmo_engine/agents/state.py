"""Pydantic models for every object that crosses an agent boundary (§9).

These are the typed contracts between the LangGraph nodes. The graph state
(`PipelineState`) carries them through the closed-loop flow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from pmo_engine import config


# --- 1. Intake -------------------------------------------------------------
class ProjectInput(BaseModel):
    """Structured project intake derived from the raw SOW (Step 1)."""
    title: str = "Untitled Project"
    summary: str = ""
    objectives: list[str] = Field(default_factory=list)
    scope: str = ""
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    timeline: str = ""
    budget: str = ""
    raw_sow: str = ""


# --- 2. Draft plan ---------------------------------------------------------
class PlanSection(BaseModel):
    """One knowledge-area section of the generated plan."""
    knowledge_area: str            # e.g. "Scope" — drives the retrieval filter
    title: str
    content: str
    key_elements: list[str] = Field(default_factory=list)


class DraftPlan(BaseModel):
    project_title: str = ""
    approach: str = ""
    wbs: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    sections: list[PlanSection] = Field(default_factory=list)


# --- 3. Validation ---------------------------------------------------------
class Citation(BaseModel):
    chapter_number: int
    chapter_title: str = ""
    section_path: str = ""
    page_start: int = 0
    page_end: int = 0
    knowledge_base: str = ""   # which source book this came from

    def book(self) -> str:
        from pmo_engine import config
        return config.kb_abbrev(self.knowledge_base)

    def display(self) -> str:
        pages = (f"p.{self.page_start}" if self.page_start == self.page_end
                 else f"pp.{self.page_start}-{self.page_end}")
        return f"{self.book()} Ch.{self.chapter_number} ({self.chapter_title}), {pages}"


class ValidationFinding(BaseModel):
    knowledge_area: str
    finding_type: str            # "alignment" | "gap" | "risk_flag"
    severity: str = "medium"     # low | medium | high
    statement: str               # what was found
    evidence: str = ""           # what RITA says
    citations: list[Citation] = Field(default_factory=list)  # REQUIRED for traceability


class SectionScore(BaseModel):
    knowledge_area: str
    score: int = 0               # 0-100 PMO compliance for this section
    rationale: str = ""


class ValidationReport(BaseModel):
    alignment_summary: str = ""
    findings: list[ValidationFinding] = Field(default_factory=list)
    section_scores: list[SectionScore] = Field(default_factory=list)
    overall_compliance_score: int = 0   # 0-100
    second_opinion: Optional[str] = None  # optional Gemini cross-check note

    def gaps(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.finding_type == "gap"]

    def risk_flags(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.finding_type == "risk_flag"]


# --- 4. Gap & Risk ---------------------------------------------------------
class RiskGapItem(BaseModel):
    category: str                # "gap" | "risk"
    knowledge_area: str = ""
    title: str = ""
    description: str = ""
    severity: str = "medium"     # low | medium | high
    likelihood: str = ""        # for risks
    impact: str = ""
    mitigation: str = ""
    citations: list[Citation] = Field(default_factory=list)


class RiskGapList(BaseModel):
    items: list[RiskGapItem] = Field(default_factory=list)

    def ranked(self) -> list[RiskGapItem]:
        order = {"high": 0, "medium": 1, "low": 2}
        return sorted(self.items, key=lambda i: order.get(i.severity, 1))


# --- 5. Recommendations ----------------------------------------------------
class Recommendation(BaseModel):
    knowledge_area: str = ""
    recommendation: str = ""
    rationale: str = ""
    priority: str = "medium"     # low | medium | high
    addresses: str = ""          # which gap/risk this targets
    citations: list[Citation] = Field(default_factory=list)


class Recommendations(BaseModel):
    items: list[Recommendation] = Field(default_factory=list)


# --- 6. Optimized plan -----------------------------------------------------
class OptimizedPlan(BaseModel):
    project_title: str = ""
    executive_summary: str = ""
    sections: list[PlanSection] = Field(default_factory=list)
    changes_from_draft: list[str] = Field(default_factory=list)  # diff vs draft
    compliance_score: int = 0
    open_items: list[str] = Field(default_factory=list)


# --- Graph state -----------------------------------------------------------
class PipelineState(BaseModel):
    """Carried through the LangGraph. Optional fields fill in as nodes run."""
    run_id: str = ""
    raw_sow: str = ""
    project_input: Optional[ProjectInput] = None
    draft_plan: Optional[DraftPlan] = None
    validation_report: Optional[ValidationReport] = None
    risk_gap_list: Optional[RiskGapList] = None
    recommendations: Optional[Recommendations] = None
    optimized_plan: Optional[OptimizedPlan] = None
    # feedback-loop control
    iteration: int = 0
    max_iterations: int = 1
    needs_revision: bool = False
    errors: list[str] = Field(default_factory=list)
    log: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = {"arbitrary_types_allowed": True}
