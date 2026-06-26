# CLAUDE.md — PMO Intelligence Engine (POC)

This file is the persistent source of truth for Claude Code on this project.
Read this file fully before doing any work, every session. If anything in a
chat instruction conflicts with this file, this file wins unless the user
explicitly says they're changing the policy in CLAUDE.md (and if so, update
this file in the same turn).

---

## 1. Project Context

A PMO Manager asked for a proof-of-concept that automates the **Closed-Loop
PMO Optimization Flow** she sketched out. This is an internal tool for
project managers, not a public product.

**The 8-step flow she specified (source of truth for scope):**

1. Project Input / SOW — define scope, objectives, requirements
2. AI Plan Generation — generate initial AI strategy, approach, plan
3. PMO Validation Engine — validate feasibility, compliance, alignment
4. Gap & Risk Identification — identify gaps, risks, mitigation areas
5. AI Recommendations — actionable AI-driven recommendations
6. Optimized Plan — refine and finalize the plan
7. Feedback Loop — review outcomes, gather feedback
8. Continuous Improvement — leverage insights to refine continuously
   (loops back into step 7/the top of the cycle)

Her "Detailed User Journey" doc collapses this into 5 user-facing steps
(Project Initiation → AI Plan Generation → PMO Validation [her stated
**core differentiator**] → Recommendations & Optimization → Finalization),
with PMO Validation explicitly required to output an **alignment summary,
gap detection, risk flags, and a PMO compliance score**.

Stated value props to keep visible in the product: reduced planning effort,
improved governance and quality, faster project readiness, consistency
across teams.

**The knowledge sources (multi-book, but PMBOK is the active default):**
- *PMBOK Guide, 6th Edition* (PMBOK, ~980 pages, **digital/text PDF, no OCR**)
  — the **active knowledge base**. It's the authoritative PMI standard (RITA is
  a study guide derived from it), ingests in seconds via text extraction, and
  scores ~94-100% on the retrieval eval across all ten knowledge areas.
- *Rita Mulcahy's PMP Exam Prep, 10th Edition* (RITA, 551 pages, **scanned**)
  — **optional / NOT loaded by default.** Decision (2026-06-23): its scanned-
  PDF OCR is impractical on modest hardware (marker/surya ran ~12h on CPU
  without finishing; the 4 GB dev GPU is too small for the multi-model OCR).
  The multi-book pipeline still supports it — run `ingest_book.py` on capable
  hardware (bigger-VRAM GPU or cloud OCR) then `build_vector_store.py --rebuild`
  to fold it in. Nothing about the architecture changes.

Both are organized by PMI knowledge area; the validation engine validates plans
against whatever books are loaded (retrieval spans the union; citations name
the source book). The KB is intentionally multi-book and extensible (see §7).
Both are licensed/owned content for internal use only — never expose raw book
text outside the validation agent's internal context, never bulk-export
ingested chunks, and never commit the PDFs or derived text to a public remote.

**IMPORTANT (iteration cost):** changing the chunking strategy does NOT re-run
OCR. OCR/extraction output is cached as `data/processed/*_structured.json`;
re-chunking reads that and rebuilds the store in seconds–minutes (GPU
embeddings). The slow OCR is a one-time, per-book cost — and PMBOK has none.

PMBOK ingestion uses text-layer extraction (PyMuPDF) with structure recovered
from PMBOK's section numbering ("5.1 Plan Scope Management"), since it has no
PDF bookmarks. PMBOK chapters 4–13 are the same ten knowledge areas as RITA,
so the knowledge_area pre-filter works uniformly across both books.

### Important fact about the source PDF

`RITA_10th_Edition.pdf` is a **scanned/image-based PDF with no embedded
text layer** (confirmed: `pdffonts` returns zero fonts, `pdftotext` returns
nothing). Every ingestion approach must start from OCR / layout-aware
extraction, not naive `pdftotext`/`pypdf` text extraction. See Section 5.

### Confirmed book structure (use this for metadata tagging — verified by inspection)

| Ch. | Title | Maps to plan section (knowledge area) | Notes |
|---|---|---|---|
| 1 | Tricks of the Trade for Studying for This Exam | — (exam-meta) | Tag `content_type=exam_tip` |
| 2 | Framework | cross-cutting | PM fundamentals, org context, project selection, roles |
| 3 | Processes and Domains | cross-cutting | Process groups/domains — used to scaffold plan generation |
| 4 | Integration | Integration / governance | Charter, PM plan, change control, closing |
| 5 | Scope | Scope | WBS, requirements, scope statement |
| 6 | Schedule | Schedule | Timeline, milestones |
| 7 | Cost | Cost | Budget |
| 8 | Quality | Quality | QA/QC, quality tools |
| 9 | Resources | Resources | Team plan |
| 10 | Communications | Communications | Comms plan |
| 11 | Risk | Risk | Risk register, response planning |
| 12 | Procurement | Procurement | Contracts |
| 13 | Stakeholders | Stakeholders | Stakeholder register/engagement |
| 14 | Tips for Passing the PMP Exam the First Time | — (exam-meta) | Contains **"Common Project Management Errors and Pitfalls"** — high value for the Gap & Risk agent. Tag `content_type=common_pitfall` |
| — | Endnotes (p.507+) | — | Ingest at low priority for citation lookups only |
| — | Index (p.523+) | — | **Exclude from ingestion** — page/term list only, no retrievable prose |

This table is the backbone of the metadata-filtered retrieval strategy in
Section 6 — chapters 5–13 map almost 1:1 to the sections of a generated
project plan, which is the single biggest "smart retrieval" lever available
here: filter by knowledge area before doing similarity search.

---

## 2. Non-Negotiable Operating Rules (read this every session)

These exist because re-running setup wastes time and money. Follow them
exactly.

1. **Conda environment name is `pmo-intel-engine`. Never create a second
   environment, never rename it, never `pip install` into base/system
   Python.**
2. **Before running anything, run `conda activate pmo-intel-engine` and
   nothing else.** Do not run `conda env create`, `conda install`, or
   `pip install` again unless:
   - the environment does not exist yet (first-ever setup), or
   - `environment.yml` has changed since the environment was last built
     and the user explicitly asks you to sync it, or
   - the user explicitly asks you to add a new dependency.
3. **Check before you install.** Before installing anything, run
   `conda env list` to see if `pmo-intel-engine` already exists. If it
   exists, activate it and move on — do not reinstall.
4. **Never re-run book ingestion (OCR → chunk → embed → load into Chroma)
   if `data/chroma_db/` already exists and is populated.** Check first
   (e.g. `python scripts/check_vector_store.py` or a quick collection
   count). Only rebuild if the user explicitly passes `--rebuild` intent
   or asks you to.
5. **Never hardcode API keys.** Keys live only in `.env` (gitignored).
   `.env.example` holds placeholders only. If a key is missing when you
   need it, stop and ask the user for it by name — don't fabricate a key,
   don't proceed with a fake one, don't skip the step silently.
6. **Don't silently swap in a different LLM/embedding provider** than what
   this file specifies. If Groq/Gemini free-tier limits or model names
   have changed since this file was written (they change often — see
   Section 4), tell the user what you found and propose the update; don't
   just substitute something else without saying so.

### Run instructions (use exactly this, every time)

```bash
# Every session, start here:
conda activate pmo-intel-engine

# First-ever setup only (skip if env already exists):
conda env create -f environment.yml
conda activate pmo-intel-engine
cp .env.example .env   # then STOP and ask the user to paste in real keys

# One-time knowledge base build (skip if data/chroma_db/ is already populated):
python scripts/ingest_book.py --pdf "data/raw/RITA 10th Edition.pdf"  # RITA (OCR, slow)
python scripts/ingest_pmbok.py                                         # PMBOK (text, fast)
python scripts/build_vector_store.py   # builds ONE combined store from all
                                       # ingested books (--rebuild to force)

# Watch a long build (RITA OCR especially):
python scripts/build_status.py --watch

# Sanity-check retrieval before building agents on top of it:
python scripts/eval_retrieval.py

# Build the frontend once (skip if app/spa/ already exists):
cd frontend && npm install && npm run build && cd ..

# Run the app (FastAPI + Uvicorn, serves the built SPA):
uvicorn app.main:app --reload   # then open http://127.0.0.1:8000

# Run tests:
pytest tests/ -v
```

---

## 3. Architecture Overview

```
SOW / RFP  (PDF upload → PyMuPDF text extraction, or pasted text)
        │
        ▼
 [1. Intake Agent] ──────────────► ProjectInput (structured)
        │
        ▼
 [2. Plan Generation Agent] ─────► DraftPlan (WBS, milestones, schedule,
        │                          per-knowledge-area sections)
        ▼
 [3. PMO Validation Agent] ◄────── Hybrid RAG over RITA knowledge base,
        │  (core differentiator)   filtered per knowledge area
        ▼
 ValidationReport (alignment summary, gap list, risk flags,
        │           PMO compliance score per section + overall)
        ▼
 [4. Gap & Risk Agent] ──────────► RiskGapList (severity-ranked, cross-refs
        │                          Risk chapter + Ch.14 common pitfalls)
        ▼
 [5. Recommendation Agent] ──────► Recommendations (RAG-grounded, cites
        │                          chapter + page)
        ▼
 [6. Finalization/Optimizer Agent] ► OptimizedPlan + exportable report
        │                            (compliance score, citations, diff
        │                            vs draft)
        ▼
 [7/8. Feedback capture] ────────► stored locally, feeds future iteration
        (loops back conceptually to step 2 for the next planning cycle)
```

This is implemented as a **LangGraph** state graph (not a single prompt,
not a simple chain) so the conditional branching and the feedback loop in
steps 7–8 are first-class, matching the PMO manager's flowchart instead of
flattening it into one linear call.

### Tech stack (decided — don't relitigate without discussing with the user)

| Layer | Choice | Why |
|---|---|---|
| OCR / structure extraction | **marker-pdf** (local, free) | The book is scanned with no text layer. marker does layout-aware OCR *and* outputs structured Markdown with heading levels intact, which is what makes header-based chunking possible. Fallback: PyMuPDF render + Tesseract for pages marker mangles (tables, formula blocks). |
| Chunking | Custom hierarchical, header-aware splitter over marker's Markdown output | See Section 5. |
| Embeddings | **BAAI/bge-large-en-v1.5** (upgraded from bge-base, 2026-06-23) via `sentence-transformers`, local; **fp16 on GPU** | Stronger retrieval; fp16 keeps it well within 4 GB. Runs on **GPU when available** (CUDA torch; `config.resolve_device()`/`config.use_fp16()`), else CPU. **Contextual retrieval:** each chunk is embedded/BM25-indexed with a breadcrumb prefix (`[PMBOK \| Risk \| 11.3 Plan Risk Responses]`) while the stored/displayed text stays clean. The dev GPU is a 4 GB RTX 3050 — fine for embeddings/reranking but **too small for marker's multi-model OCR**, so OCR stays on CPU. |
| Sparse retrieval | **rank_bm25**, local | PM terminology (WBS, EVM, ITTO, specific PMI terms) needs exact-match alongside semantic search. |
| Reranking | **BAAI/bge-reranker-v2-m3** (upgraded from MiniLM-L-6, 2026-06-23) via `sentence-transformers`, fp16 on GPU; auto-fallback to `bge-reranker-base` → MiniLM on VRAM/load failure | Stronger cross-encoder reranking of the top-20 shortlist. fp16 fit verified (peak 3.46 GB with bge-large). |
| Vector store | **ChromaDB**, persisted to `data/chroma_db/` | Zero infra, runs inside the conda env, good metadata filtering. |
| Agent orchestration | **LangGraph** | Matches the closed-loop flow including the feedback loop edge; gives conditional branching for free instead of hand-rolling a state machine. |
| LLM — primary | **Groq**, `llama-3.3-70b-versatile` for reasoning-heavy steps (validation synthesis, recommendations); `llama-3.1-8b-instant` for cheap/high-volume steps (intake extraction, sub-query generation, classification) | Fast, generous-enough free tier, and routing cheap vs. expensive calls to different models inside the same pipeline matters because free-tier daily request caps are tight (see Section 4). |
| LLM — fallback | **Google Gemini**, `gemini-2.5-flash` | Used when Groq is rate-limited or for a second opinion on validation scoring. Do **not** use `gemini-2.0-flash` or `gemini-1.5-flash` — both are deprecated as of 2026; confirm current free-tier model IDs against `ai.google.dev` before hardcoding. |
| UI | **FastAPI + Uvicorn backend + React SPA (Vite + Tailwind + shadcn/ui + Recharts)** | Per user direction (2026-06-21/22): replaced Streamlit, then upgraded the hand-rolled SPA to React + Tailwind + shadcn/ui for a polished, full-screen UI with analytics charts (radial compliance gauge, per-section score bars, gap/risk pies). FastAPI streams NDJSON step-progress and serves the Vite build from `app/spa/`. Node is in the conda env; rebuild with `cd frontend && npm run build`. |
| Input | **PDF upload (SOW / RFP)** via `POST /api/upload-sow`, or pasted text | Real intake is a PDF, so the UI accepts a PDF upload; text is extracted server-side with PyMuPDF and shown in an editable box before running. Scanned (no-text) PDFs are rejected with a clear message. A realistic sample lives in `sample/` (downloadable + uploadable to demo the flow). |
| Feedback storage | Local SQLite (`data/feedback.db`) | Enough for a POC; this is where the "Step 7/8" loop is instrumented, not a full retraining pipeline (see Section 7). |

This stack is intentionally light on framework abstraction outside of
LangGraph — each agent calls the LLM clients directly so prompts are
debuggable and the system stays demoable without a lot of moving parts.

---

## 4. LLM Provider Notes (verify before relying on these — they go stale fast)

As of mid-2026, free-tier reality looks like this. **These numbers and
model names change frequently — if you're picking up this project after a
gap, re-check `console.groq.com/docs/models` and `ai.google.dev/gemini-api/docs/rate-limits`
before assuming the below is still accurate, and flag it to the user if
it's drifted.**

- **Groq free tier**: no credit card, access to every hosted model, but
  tight per-model caps — `llama-3.3-70b-versatile` is roughly 30 RPM /
  1,000 requests per day; `llama-3.1-8b-instant` is far more permissive
  (~14,400 requests/day). This is why the pipeline routes cheap steps to
  the 8B model and reserves the 70B model for the validation/recommendation
  steps that actually need the reasoning quality.
- **Gemini free tier**: Pro models were pulled from the free tier in
  April 2026 — **free tier is Flash/Flash-Lite only now.** `gemini-2.5-flash`
  is the safe default; check whether `gemini-3-flash` or
  `gemini-3.1-flash-lite` are available and a better fit at build time.
  Free tier usage may be used by Google to improve their models — don't
  send anything outside the RITA book content + synthetic test SOWs
  through Gemini during the POC.
- Build in **exponential backoff + provider fallback** (Groq → Gemini) from
  the start, not as an afterthought — free-tier 429s are routine, not
  exceptional, at these volumes.

---

## 5. Chunking Strategy (the "smart, use-case-based" part)

Goal: chunks that are precise enough for targeted retrieval, but coherent
enough that the PMO Validation Agent gets a complete thought, with metadata
that lets the agent filter to the right knowledge area *before* it does
any similarity search at all.

1. **OCR to structured Markdown first.** Run the whole book through
   `marker-pdf` once. This produces Markdown with heading levels (`#`
   chapter, `##` major section, `###` subsection) preserved — this is what
   turns "chunk a 551-page scanned book intelligently" from a hard problem
   into a tractable one. Spot-check ~10–15 pages across different chapters
   (especially ones with tables/diagrams, e.g. the ITTO tables and EVM
   formula pages) against the rasterized originals; where marker garbles a
   page, fall back to PyMuPDF render + Tesseract for that page only, or a
   vision-LLM pass (Gemini) as a last resort for that page.

2. **Primary split: by heading hierarchy**, not fixed token windows. Each
   leaf section (typically an `###` subsection, e.g. "Validate and Control
   Scope" under Chapter 5) becomes a candidate chunk. This respects the
   book's own organization instead of cutting sentences at arbitrary
   boundaries.

3. **Content-type-aware handling within sections:**
   - **ITTO tables/lists** (Inputs/Tools & Techniques/Outputs) — keep
     intact as one atomic chunk regardless of size; never split a table
     across chunks. Tag `content_type=itto`.
   - **Formulas** (EVM formulas, etc.) — keep the formula and its worked
     example/explanation together as one chunk. Tag `content_type=formula`.
   - **Definitions/glossary-style terms** — small atomic chunks.
     Tag `content_type=definition`.
   - **"Tricks of the Trade" / PMI-isms (Ch.1) and "Common Errors and
     Pitfalls" (Ch.14)** — chunk separately and tag `content_type=exam_tip`
     or `content_type=common_pitfall`. These feed the Gap & Risk agent
     directly — they're literally a curated list of "what PMOs/PMI flag as
     mistakes," which is exactly what that agent needs to check generated
     plans against.
   - **Narrative/process description** (the bulk of the book) — tag
     `content_type=concept`.

4. **Sizing**: target ~300–600 tokens per chunk (use `tiktoken`
   `cl100k_base` purely as a length heuristic, not because we're calling
   an OpenAI model). If a leaf section is longer than ~600 tokens, split
   it with a recursive splitter using ~15% overlap *while keeping any
   ITTO table or formula block from #3 intact even if that means an
   individual chunk runs longer than the target*. If a leaf section is
   very short (a one-line subsection), merge it with its parent section's
   intro text rather than emitting a near-empty chunk.

5. **Required metadata per chunk** (store as Chroma metadata, not just in
   the text): `chapter_number`, `chapter_title`, `knowledge_area` (per the
   Section 1 table), `section_path` (e.g. "Ch.5 Scope > Validate and
   Control Scope"), `page_start`, `page_end`, `content_type`,
   `process_group` (Initiating/Planning/Executing/Monitoring&Controlling/
   Closing, when determinable). `page_start`/`page_end` are required so
   the Validation Agent can cite "RITA Ch.5, p.150" in its output — this
   matters for a governance/compliance tool; PMO stakeholders will want
   to trace a claim back to a page.

6. **Parent-document (small-to-big) retrieval**: store the small,
   precisely-tagged chunks above as what gets embedded and searched, but
   also persist each chunk's full parent section text (in a lightweight
   local store, e.g. a JSON/SQLite lookup keyed by `section_path`). At
   retrieval time, search against the small chunks for precision, then
   expand to the parent section before handing context to the LLM, so the
   model isn't reasoning over a fragment stripped of surrounding context.

7. **Chapter-level summary chunks**: in addition to the above, generate
   one short (3–5 sentence) LLM-written summary per chapter and store it
   as its own tagged chunk (`content_type=chapter_summary`). These power a
   coarse first-pass retrieval/routing step — useful when the Validation
   Agent needs to decide *which* knowledge areas are even relevant to a
   given plan section before drilling into fine-grained chunks.

8. Exclude the **Index** (page-number/term list, no retrievable prose).
   Ingest **Endnotes** but at low retrieval priority (citation lookup only,
   don't surface them as primary validation evidence).

---

## 6. Retrieval Strategy

1. **Metadata-filter first, search second.** Each plan section the
   Validation Agent checks (Scope, Schedule, Cost, …) maps directly to a
   `knowledge_area` filter via the Section 1 table — apply that filter in
   Chroma *before* running similarity search, not after. This is the
   single biggest precision win available given how cleanly this book maps
   to typical project plan sections.

2. **Hybrid search**: combine dense (embedding cosine similarity) and
   sparse (BM25) retrieval, fused with Reciprocal Rank Fusion (RRF), not a
   hand-tuned weighted average. PM acronyms and exact terminology (WBS,
   EVM, RACI, ITTO) benefit from exact-match that pure embeddings can miss.

3. **Multi-query per validation step, not one big query.** For each plan
   section being validated, the Validation Agent should generate 2–4
   targeted sub-queries (e.g., "what should a risk register contain",
   "schedule baseline requirements", "WBS decomposition best practices")
   rather than embedding the entire plan section as one query. Use the
   cheap/high-volume Groq model (`llama-3.1-8b-instant`) for this
   query-generation step.

4. **Rerank the fused shortlist.** Retrieve top ~20 via hybrid search,
   rerank with the local cross-encoder down to the top ~5 that actually go
   into the LLM's context window. This is a local model call — no API
   budget spent on it.

5. **Expand to parent section** (Section 5.6) for the final top results
   before constructing the prompt context.

6. **Always carry citations through.** Every retrieved chunk keeps its
   `section_path` and page range; every validation finding and
   recommendation in the final output should cite back to a specific
   chapter/page, not just a vague "per PMI best practices."

7. **Coarse-to-fine routing using chapter summaries** (Section 5.7) is
   optional for v1 but worth wiring in: a single LLM call can scan the 14
   chapter summaries and shortlist which knowledge areas are even relevant
   before the per-section fine retrieval starts — saves retrieval calls on
   irrelevant chapters for unusual project types.

8. **Build `scripts/eval_retrieval.py` as a real sanity check**, not a
   throwaway: a small fixed set of test queries (e.g., "what are the
   inputs to Develop Project Charter", "list the risk response strategies",
   "what's in a stakeholder register") with the expected chapter as the
   known-correct answer, asserting the right chapter shows up in the top-3
   results. Run this after any change to chunking/embedding before
   touching the agents — if retrieval is wrong, nothing built on top of it
   can be trusted.

---

## 7. Scope Notes for This POC

- The **Feedback Loop / Continuous Improvement** steps (7–8 in her
  flowchart) are implemented as **instrumentation, not automation**, for
  this POC: capture user ratings/comments on the OptimizedPlan into
  `data/feedback.db`, and surface a simple aggregate view (most common
  gap types flagged across runs) in the Streamlit app. Actually retraining
  or auto-tuning prompts from that feedback is out of scope for the POC —
  say so explicitly in the README as a "Phase 2" item rather than quietly
  skipping it.
- The knowledge base is built to be **extensible beyond RITA** even though
  RITA is the only source for v1 — her deck explicitly says "alignment
  with PMI **and firm best practices**," implying internal governance
  docs get added later. Keep the ingestion pipeline generic (a
  `knowledge_base` concept that RITA is the first member of), not
  hardcoded to one PDF, so a second internal-policy document can be added
  later without a redesign.
- This is a POC for a demo to a PMO manager, not a production system.
  Prioritize a working end-to-end pipeline with a clean Streamlit
  walkthrough over exhaustive production hardening (auth, multi-tenant
  storage, etc.) — but don't cut corners on the RAG quality itself, since
  validation/compliance scoring quality is the actual point being
  demonstrated.

---

## 8. Repository Structure

```
pmo-intelligence-engine/
├── CLAUDE.md
├── README.md
├── environment.yml
├── .env.example
├── .env                      # gitignored — real keys live here only
├── .gitignore
├── data/
│   ├── raw/                  # RITA_10th_Edition.pdf goes here
│   ├── processed/            # marker output markdown + extracted images
│   ├── chroma_db/            # persisted vector store (gitignored)
│   └── feedback.db           # local feedback capture (gitignored)
├── scripts/
│   ├── ingest_book.py        # OCR + structure extraction (marker-pdf)
│   ├── build_vector_store.py # chunk → embed → load into Chroma
│   ├── check_vector_store.py # quick "is it already built?" check
│   └── eval_retrieval.py     # retrieval sanity-check harness
├── src/pmo_engine/
│   ├── config.py              # env/config loader, model names, chunk sizes
│   ├── ocr/extract_structure.py
│   ├── chunking/hierarchical_chunker.py
│   ├── retrieval/
│   │   ├── vector_store.py    # Chroma wrapper
│   │   ├── bm25_index.py
│   │   ├── hybrid_retriever.py # RRF fusion + metadata filter
│   │   └── reranker.py
│   ├── llm/
│   │   ├── groq_client.py
│   │   ├── gemini_client.py
│   │   └── router.py          # provider fallback + cheap/expensive routing
│   ├── agents/
│   │   ├── state.py            # pydantic schemas for all pipeline objects
│   │   ├── intake_agent.py
│   │   ├── plan_generation_agent.py
│   │   ├── pmo_validation_agent.py
│   │   ├── gap_risk_agent.py
│   │   ├── recommendation_agent.py
│   │   ├── finalization_agent.py
│   │   └── graph.py             # LangGraph wiring incl. feedback loop edge
│   └── feedback/feedback_store.py
├── app/                      # FastAPI backend + built SPA
│   ├── main.py               # API routes + NDJSON streaming; serves app/spa
│   └── spa/                  # Vite build output (gitignored; npm run build)
├── frontend/                 # React + Vite + Tailwind + shadcn/ui + Recharts
│   ├── src/{App.jsx,main.jsx,components/,lib/}
│   ├── package.json, vite.config.js, tailwind.config.js
│   └── (node_modules gitignored)
├── sample/                   # demo input: AI Future Operating Model SOW
│   ├── AI_Future_Operating_Model_SOW.md   # source
│   └── AI_Future_Operating_Model_SOW.pdf  # uploadable demo PDF (6 pages)
├── tests/
└── outputs/                   # exported optimized plans
```

---

## 9. Coding Conventions

- Python 3.11, type hints everywhere, pydantic models for every structured
  object that crosses an agent boundary (`ProjectInput`, `DraftPlan`,
  `ValidationReport`, `RiskGapList`, `Recommendations`, `OptimizedPlan`).
- `logging`, not `print`, for anything beyond a CLI script's final output.
- No secrets in code, no secrets in logs.
- Every module that calls an LLM should go through `llm/router.py`, never
  call the Groq/Gemini SDKs directly from agent code — that's where
  fallback and cheap/expensive routing live, and it needs to stay
  centralized.

---

## 10. Build Status

Update this checklist as work progresses — it's how a new session picks up
where the last one left off.

Legend: [x] done/validated · [~] code-complete, runtime pending · [ ] not started

- [x] Conda env created (`pmo-intel-engine`) — verified all deps import
- [x] `.env.example` created, `.env` created (REAL KEYS STILL PENDING FROM USER)
- [~] Book OCR/structure extraction pipeline working (`scripts/ingest_book.py`)
      — code complete; running unattended via scripts/_finish_build.py (marker
      model download is CDN-throttled, then 551-page CPU OCR; see NOTES.md)
- [~] Hierarchical chunker implemented + spot-checked against source pages
      — implemented + 4 unit tests pass; spot-check vs real OCR pending the
      finisher run
- [~] Vector store built (`data/chroma_db/`), BM25 index built — build script
      complete; runs in the finisher chain after OCR
- [x] Hybrid retriever + reranker implemented (RRF + cross-encoder + parent exp.)
- [~] `scripts/eval_retrieval.py` — harness complete with fixed test set;
      runs as the last step of the finisher chain
- [x] LLM router (Groq primary + Gemini fallback, backoff, cheap/reason routing)
      — validated with real keys (Groq 429 backoff + Gemini fallback both fired)
- [x] Intake Agent — validated end-to-end (scripts/_smoke_pipeline.py)
- [x] Plan Generation Agent — validated (10 KA sections generated)
- [x] PMO Validation Agent (core differentiator — citations grounded in real
      chunk metadata) — validated: per-section + overall score, cited findings
- [x] Gap & Risk Identification Agent (cross-refs Ch.11 + Ch.14 pitfalls) — validated
- [x] Recommendation Agent (RAG-grounded, cited) — validated
- [x] Finalization/Optimizer Agent (diff vs draft + revision flag) — validated
- [x] LangGraph wiring end-to-end, including feedback loop edge — validated
- [x] Feedback capture storage + aggregate view (SQLite; unit-tested)
- [x] FastAPI + Uvicorn UI mirroring the 5-step user journey (replaced
      Streamlit) — server + index + static + APIs validated (HTTP 200)
- [x] README with setup + demo-script instructions for the PMO manager walkthrough

Whole agent pipeline + web stack VALIDATED with real keys against a synthetic
KB. The only thing the background finisher (`scripts/_finish_build.py`) adds is
the real RITA knowledge-base content; no code path is gated on it. When it
prints "FINISHER COMPLETE", run `python scripts/check_vector_store.py` and
`python scripts/eval_retrieval.py`, then `uvicorn app.main:app`.