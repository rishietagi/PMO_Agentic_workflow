# Project — PMO Intelligence Engine (POC)

Precise statement of what this project is, who it's for, what's in/out of
scope, and current status. For implementation see
[ARCHITECTURE.md](ARCHITECTURE.md); for tooling see
[TECH_STACK.md](TECH_STACK.md).

---

## 1. Problem & audience

A PMO manager needs to turn raw project intake (SOW) into a governed,
PMI-aligned project plan faster and more consistently. Today this is manual,
inconsistent across teams, and hard to audit. **Audience:** internal project
managers / PMO — not a public product.

**Goal of this POC:** demonstrate an automated **Closed-Loop PMO Optimization
Flow** that generates a plan, validates it against an authoritative PM
reference, scores compliance, surfaces gaps/risks, recommends grounded fixes,
and captures feedback — with every claim traceable to a source page.

---

## 2. The flow (product spec — source of truth)

8-step flow the manager specified:

1. Project Input / SOW
2. AI Plan Generation
3. PMO Validation Engine
4. Gap & Risk Identification
5. AI Recommendations
6. Optimized Plan
7. Feedback Loop
8. Continuous Improvement (loops back to 7 / the top)

Collapsed into **5 user-facing steps** in the UI: Project Initiation → AI Plan
Generation → **PMO Validation** *(the stated core differentiator)* →
Recommendations & Optimization → Finalization. PMO Validation must output an
**alignment summary, gap detection, risk flags, and a PMO compliance score**.

**Value props kept visible:** reduced planning effort, improved governance &
quality, faster project readiness, consistency across teams.

---

## 3. Knowledge sources (multi-book; PMBOK active)

1. *PMBOK Guide, 6th Edition* (PMBOK) — ~980 pages, **digital text PDF (no
   OCR)**. The **active knowledge base**: the authoritative PMI standard,
   ingests in seconds, covers all ten knowledge areas (chapters 4–13), ~94-100%
   retrieval eval.
2. *Rita Mulcahy's PMP Exam Prep, 10th Edition* (RITA) — 551 pages, **scanned
   (OCR)**. **Optional / not loaded by default** — decision 2026-06-23: its OCR
   is impractical on modest hardware (~12h on CPU without finishing; 4 GB GPU
   too small). The multi-book pipeline supports adding it later on capable
   hardware with no redesign. (RITA is a study guide derived from PMBOK, so
   PMBOK-only is the more authoritative grounding, not a downgrade.)

Books are ingested into one vector store; each chunk is tagged with its
`knowledge_base`, retrieval spans whatever is loaded, and every citation names
the source book (e.g. "PMBOK Ch.11, p.397"). The KB is extensible: a third
source = one registry entry + one ingest step. **Iteration note:** chunking
changes don't re-OCR — extraction output is cached as `*_structured.json`, so
rebuilds are seconds–minutes.

**Licensing:** internal-use content. Never expose raw book text outside the
validation context, never bulk-export chunks, never commit the PDFs or derived
text to a public remote (enforced via `.gitignore`).

---

## 4. What the system produces

- **ProjectInput** — structured intake from the SOW.
- **DraftPlan** — approach, WBS, milestones, one section per knowledge area.
- **ValidationReport** — per-section + overall compliance score (0–100),
  alignment summary, and cited findings (alignment / gap / risk_flag).
- **RiskGapList** — severity-ranked gaps & risks, cross-referencing the Risk
  chapter and Ch.14 pitfalls, with mitigations and citations.
- **Recommendations** — prioritized, RAG-grounded, cited fixes.
- **OptimizedPlan** — executive summary, a diff vs. the draft, carried
  compliance score, open items.
- **Feedback** — ratings/comments + flagged-gap aggregates.

Every finding and recommendation cites a specific chapter/page, naming the source book (e.g. "PMBOK Ch.11, p.397").

---

## 5. Scope

**In scope (POC):**
- End-to-end pipeline from SOW → optimized, scored, cited plan.
- Hybrid RAG (metadata-filtered, dense+sparse, reranked, parent-expanded) over
  the PMBOK content (bge-large + bge-reranker-v2-m3 + contextual breadcrumbs).
- LangGraph orchestration including the feedback-loop edge.
- Polished web UI (React/Tailwind/shadcn/Recharts/framer-motion): a unified
  executive dashboard (Project Readiness Index, compliance gauge, KA radar +
  compliance heatmap, likelihood×impact risk matrix) plus a per-step analytics
  tab for each PMO stage. PDF (SOW/RFP) upload via PyMuPDF, or pasted text.
- Feedback capture + aggregate dashboard.

**Out of scope (explicitly Phase 2):**
- Auto-retraining / prompt auto-tuning from feedback — feedback is
  **instrumentation only** for the POC.
- Auth, multi-tenant storage, role-based access.
- Additional knowledge sources beyond RITA (the pipeline is built generic — a
  `knowledge_base` concept — so internal governance docs can be added later
  without redesign).
- Production hardening (rate-limit quotas at scale, observability, CI/CD).

---

## 6. Key design decisions (and rationale in brief)

- **Citations grounded in chunk metadata, not LLM output** — required for a
  governance/compliance tool; makes claims auditable and turns "hallucinated
  citation" into a detectable retrieval bug.
- **Metadata-filter-before-search** by knowledge area — biggest precision lever
  given the clean chapter↔plan-section mapping.
- **Cheap/reasoning LLM routing + Groq→Gemini fallback** — free-tier daily caps
  are tight; cheap steps (intake, sub-queries) use the 8B model, reasoning
  steps use 70B, with backoff and a Gemini fallback.
- **LangGraph (not a linear chain)** — makes the conditional feedback loop
  (steps 7–8) first-class instead of flattening the manager's flowchart.

---

## 7. Status (POC)

- **Code:** complete across all phases — env, multi-book ingestion, chunking,
  retrieval, LLM router, all 6 agents, LangGraph, feedback store, React/FastAPI
  UI, docs.
- **Active knowledge base:** **PMBOK 6th** (text extraction, no OCR) — 543
  chunks across all ten knowledge areas, **100% chapter@5** and ~93% passage@1
  on the retrieval eval. RITA is supported but optional (OCR impractical on the
  dev hardware).
- **Retrieval (GPU):** bge-large-en-v1.5 embeddings + bge-reranker-v2-m3
  (fp16), contextual breadcrumb embedding, hybrid RRF + parent expansion.
- **UI:** unified executive dashboard (Project Readiness Index + scoring,
  KA radar, compliance heatmap, risk matrix) + per-step analytics tabs;
  PDF (SOW/RFP) upload.
- **Resilience:** the LLM router retries Groq (429) and Gemini (503/overload)
  with backoff, then degrades a reasoning step to the high-cap 8B model so a
  transient provider outage doesn't fail a run.
- **Validated:** full agent pipeline with real keys via
  `scripts/_smoke_pipeline.py`; FastAPI serving the SPA; 18 unit tests passing;
  retrieval eval via `scripts/eval_retrieval.py [--detailed]`.

---

## 8. How to demo

`uvicorn app.main:app` → http://127.0.0.1:8000 → **Run pipeline** on the
pre-loaded sample SOW → open the **Validation** tab (compliance gauge,
per-section bars, citation chips) → **Gaps · Risks · Recs** → **Optimized
Plan** (diff) → submit **Feedback** → **Feedback dashboard**. Validation steps
are in `README.md` ("How to validate the pipeline").
