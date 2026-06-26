"""LangGraph state graph wiring the closed-loop PMO flow (the design spec).

    intake -> plan_generation -> validation -> gap_risk -> recommendations
           -> finalization --(needs_revision?)--> validation (loop) | END

The conditional edge from finalization back to validation is the first-class
feedback-loop edge (flow steps 7-8): if overall compliance is below threshold
and we haven't hit max_iterations, the optimized plan is fed back in as the new
draft and re-validated, demonstrating continuous improvement rather than a
single linear pass.
"""
from __future__ import annotations

import logging
import uuid

from langgraph.graph import END, StateGraph

from pmo_engine.agents.finalization_agent import (REVISION_THRESHOLD,
                                                  FinalizationAgent)
from pmo_engine.agents.gap_risk_agent import GapRiskAgent
from pmo_engine.agents.intake_agent import IntakeAgent
from pmo_engine.agents.plan_generation_agent import PlanGenerationAgent
from pmo_engine.agents.pmo_validation_agent import PMOValidationAgent
from pmo_engine.agents.recommendation_agent import RecommendationAgent
from pmo_engine.agents.state import DraftPlan, PipelineState
from pmo_engine.llm.router import LLMRouter, get_router
from pmo_engine.retrieval.hybrid_retriever import HybridRetriever

logger = logging.getLogger(__name__)


class PMOEngine:
    """Builds the agents once and compiles the LangGraph."""

    def __init__(self, router: LLMRouter | None = None,
                 retriever: HybridRetriever | None = None,
                 second_opinion: bool = False,
                 max_iterations: int = 1) -> None:
        self.router = router or get_router()
        self.retriever = retriever or HybridRetriever()
        self.max_iterations = max_iterations
        self.intake = IntakeAgent(self.router)
        self.plangen = PlanGenerationAgent(self.router)
        self.validator = PMOValidationAgent(self.router, self.retriever,
                                            second_opinion=second_opinion)
        self.gaprisk = GapRiskAgent(self.router, self.retriever)
        self.recommender = RecommendationAgent(self.router, self.retriever)
        self.finalizer = FinalizationAgent(self.router)
        self.graph = self._build()

    # --- nodes ------------------------------------------------------------
    def _n_intake(self, s: PipelineState) -> dict:
        pi = self.intake.run(s.raw_sow)
        return {"project_input": pi, "log": s.log + ["intake"]}

    def _n_plangen(self, s: PipelineState) -> dict:
        plan = self.plangen.run(s.project_input)
        return {"draft_plan": plan, "log": s.log + ["plan_generation"]}

    def _n_validation(self, s: PipelineState) -> dict:
        report = self.validator.run(s.draft_plan, s.project_input)
        return {"validation_report": report, "log": s.log + ["validation"]}

    def _n_gaprisk(self, s: PipelineState) -> dict:
        rgl = self.gaprisk.run(s.draft_plan, s.validation_report)
        return {"risk_gap_list": rgl, "log": s.log + ["gap_risk"]}

    def _n_recommend(self, s: PipelineState) -> dict:
        recs = self.recommender.run(s.draft_plan, s.validation_report,
                                    s.risk_gap_list)
        return {"recommendations": recs, "log": s.log + ["recommendations"]}

    def _n_finalize(self, s: PipelineState) -> dict:
        opt = self.finalizer.run(s.draft_plan, s.validation_report,
                                 s.recommendations)
        it = s.iteration + 1
        needs = (opt.compliance_score < REVISION_THRESHOLD
                 and it < s.max_iterations)
        updates = {"optimized_plan": opt, "iteration": it,
                   "needs_revision": needs, "log": s.log + ["finalization"]}
        if needs:
            # feed the optimized plan back in as the new draft for re-validation
            updates["draft_plan"] = DraftPlan(
                project_title=opt.project_title, approach="(revised)",
                wbs=s.draft_plan.wbs, milestones=s.draft_plan.milestones,
                sections=opt.sections)
        return updates

    @staticmethod
    def _route_after_final(s: PipelineState) -> str:
        return "revise" if s.needs_revision else "end"

    def _build(self):
        g = StateGraph(PipelineState)
        g.add_node("intake", self._n_intake)
        g.add_node("plan_generation", self._n_plangen)
        g.add_node("validation", self._n_validation)
        g.add_node("gap_risk", self._n_gaprisk)
        g.add_node("recommendations", self._n_recommend)
        g.add_node("finalization", self._n_finalize)

        g.set_entry_point("intake")
        g.add_edge("intake", "plan_generation")
        g.add_edge("plan_generation", "validation")
        g.add_edge("validation", "gap_risk")
        g.add_edge("gap_risk", "recommendations")
        g.add_edge("recommendations", "finalization")
        g.add_conditional_edges("finalization", self._route_after_final,
                                {"revise": "validation", "end": END})
        return g.compile()

    # --- run helpers ------------------------------------------------------
    def initial_state(self, raw_sow: str) -> PipelineState:
        return PipelineState(run_id=uuid.uuid4().hex[:12], raw_sow=raw_sow,
                             max_iterations=self.max_iterations)

    def run(self, raw_sow: str) -> PipelineState:
        state = self.initial_state(raw_sow)
        # recursion_limit guards the loop edge
        result = self.graph.invoke(state, {"recursion_limit": 25})
        return PipelineState(**result) if isinstance(result, dict) else result

    def stream(self, raw_sow: str):
        """Yield (node_name, partial_update_dict) as each node completes —
        used by the Streamlit UI to show step-by-step progress."""
        state = self.initial_state(raw_sow)
        # emit the seed state first so callers get run_id before nodes run
        yield "start", {"run_id": state.run_id, "raw_sow": raw_sow,
                        "max_iterations": self.max_iterations}
        for event in self.graph.stream(state, {"recursion_limit": 25}):
            for node_name, update in event.items():
                yield node_name, update
