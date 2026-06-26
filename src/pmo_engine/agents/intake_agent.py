"""Agent 1 — Intake (Step 1: Project Input / SOW).

Turns a free-text SOW into a structured ProjectInput. This is a cheap,
high-volume extraction step -> CHEAP tier (8B instant) per the design spec
"""
from __future__ import annotations

import logging

from pmo_engine.agents.state import ProjectInput
from pmo_engine.llm.router import LLMRouter, TaskTier, get_router

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a PMO intake analyst. Extract a structured project definition "
    "from a Statement of Work. Return ONLY JSON with keys: title, summary, "
    "objectives[], scope, deliverables[], requirements[], constraints[], "
    "assumptions[], stakeholders[], timeline, budget. Use [] or \"\" when a "
    "field is absent — never invent facts not supported by the SOW.")


class IntakeAgent:
    def __init__(self, router: LLMRouter | None = None) -> None:
        self.router = router or get_router()

    def run(self, raw_sow: str) -> ProjectInput:
        logger.info("Intake: extracting structured project input.")
        data = self.router.complete_json(
            _SYSTEM, f"Statement of Work:\n\"\"\"\n{raw_sow}\n\"\"\"",
            tier=TaskTier.CHEAP, max_tokens=1500)
        if not data:
            logger.warning("Intake extraction empty; using minimal fallback.")
            return ProjectInput(summary=raw_sow[:500], raw_sow=raw_sow)
        data["raw_sow"] = raw_sow
        # coerce stray string fields that should be lists
        for k in ("objectives", "deliverables", "requirements", "constraints",
                  "assumptions", "stakeholders"):
            v = data.get(k)
            if isinstance(v, str):
                data[k] = [v] if v else []
        try:
            return ProjectInput(**{k: v for k, v in data.items()
                                   if k in ProjectInput.model_fields})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Intake model coercion failed (%s); fallback.", exc)
            return ProjectInput(summary=raw_sow[:500], raw_sow=raw_sow)
