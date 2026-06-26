# PMO Intelligence Engine (POC)

A proof-of-concept that automates a PMO manager's **Closed-Loop PMO
Optimization Flow**: take a project SOW, generate a PMI-aligned plan, validate
it against authoritative references (**RITA PMP Exam Prep 10th ed. + PMBOK
Guide 6th ed.**), surface gaps/risks, recommend grounded fixes, and produce an
optimized plan with a **PMO compliance score and page-level citations that name
the source book** — then capture feedback for continuous improvement.

The architecture, RAG strategy, and tech stack are documented in
[docs/](docs/). This README is the operator's guide.

---

## What it does (5-step user journey)

1. **Project Initiation** — extract a structured project definition from the SOW.
2. **AI Plan Generation** — draft a plan with WBS, milestones, and one section
   per PMI knowledge area.
3. **PMO Validation** *(core differentiator)* — hybrid RAG over the PMBOK
   knowledge base (RITA optional), filtered per knowledge area, producing an alignment summary,
   gap detection, risk flags, and a **0–100 compliance score** — every finding
   cites a chapter/page.
4. **Recommendations & Optimization** — severity-ranked gaps/risks (cross-
   referencing the Risk chapter + Ch.14 common pitfalls) and grounded,
   prioritized recommendations.
5. **Finalization** — an optimized plan with an executive summary, a diff vs.
   the draft, and the carried compliance score.

Steps 7–8 (**Feedback Loop / Continuous Improvement**) are implemented as
**instrumentation only** — ratings/comments and flagged-gap aggregates are
captured to SQLite and shown in a dashboard. Auto-retraining / prompt
auto-tuning is intentionally **out of scope for this POC (a Phase 2 item)**.

The whole pipeline is a **LangGraph** state graph including a first-class
feedback-loop edge: if compliance is low, the optimized plan is fed back in and
re-validated (bounded by a max-iterations setting).

---

## Architecture (summary)

| Layer | Choice |
|---|---|
| OCR / structure | marker-pdf (local) → structured elements; PyMuPDF+Tesseract per-page fallback |
| Chunking | custom hierarchical, content-type-aware (ITTO/formula atomic; parent-doc store) |
| Embeddings | BAAI/bge-large-en-v1.5 (local; fp16 GPU) — with contextual breadcrumb prefixes |
| Sparse | rank_bm25 (local) |
| Fusion / rerank | Reciprocal Rank Fusion + BAAI/bge-reranker-v2-m3 (local, fp16 GPU; auto-fallback) |
| Vector store | ChromaDB (persisted to `data/chroma_db/`) |
| Orchestration | LangGraph |
| LLM | Groq (`llama-3.3-70b-versatile` reasoning / `llama-3.1-8b-instant` cheap), Gemini (`gemini-2.5-flash`) fallback |
| UI | FastAPI backend + React SPA (Vite · Tailwind · shadcn/ui · Recharts · framer-motion) — exec dashboard + per-step analytics tabs |
| Feedback | SQLite (`data/feedback.db`) |
| Input | PDF upload (SOW/RFP) → PyMuPDF text extraction, or pasted text |

Retrieval is **metadata-filtered first** (knowledge_area → chapter), then
hybrid dense+sparse, fused, reranked, and parent-expanded. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Setup & run

> **Conda env name is `pmo-intel-engine`.** Never create a second env. On
> repeat sessions, just activate it — do **not** re-create or re-install.

```bash
# Every session, start here:
conda activate pmo-intel-engine

# First-ever setup only (skip if the env already exists — check: conda env list):
conda env create -f environment.yml
conda activate pmo-intel-engine
cp .env.example .env        # then paste REAL keys into .env (see below)

# One-time knowledge base build (SKIP if data/chroma_db/ is already populated —
# check first: python scripts/check_vector_store.py).
# Multi-book: ingest each source, then build ONE combined store.
python scripts/ingest_book.py --pdf "data/raw/RITA 10th Edition.pdf"  # RITA (OCR, slow, CPU)
python scripts/ingest_pmbok.py                                         # PMBOK (text, fast)
python scripts/build_vector_store.py        # combined store; GPU embeddings if available
python scripts/build_status.py              # see per-book build state anytime

# Sanity-check retrieval before trusting the agents:
python scripts/eval_retrieval.py

# Build the frontend once (skip if app/spa/ already exists):
cd frontend && npm install && npm run build && cd ..

# Run the app (FastAPI + Uvicorn, serves the built React SPA):
uvicorn app.main:app --reload      # then open http://127.0.0.1:8000
# (or: python -m app.main)

# Run tests:
pytest tests/ -v
```

> **Frontend dev mode (optional):** `cd frontend && npm run dev` starts Vite on
> :5173 with hot reload and proxies `/api` to uvicorn on :8000. For the demo,
> the pre-built SPA served by uvicorn on :8000 is all you need.

### What to skip on repeat runs
- **Don't** re-create the conda env or re-install deps.
- **Don't** re-run ingestion if `data/chroma_db/` is populated —
  `python scripts/check_vector_store.py` tells you (exit 0 = built).
- `ingest_book.py` and `build_vector_store.py` are idempotent; pass `--rebuild`
  to force.

> **Note on system Tesseract:** the per-page OCR fallback needs the Tesseract
> binary installed. It's optional — marker is the primary path and the fallback
> degrades gracefully if Tesseract isn't present.

---

## API keys

Keys live **only** in `.env` (gitignored). Get free keys:
- `GROQ_API_KEY` — https://console.groq.com/keys (required to run the agents)
- `GOOGLE_API_KEY` — https://aistudio.google.com/apikey (optional fallback /
  second opinion)

The knowledge base build and retrieval eval run **without** keys. Plan
generation, validation, gap/risk, recommendations, and finalization **require**
a Groq key (Gemini is the fallback).

Verified model IDs (2026-06-21): `llama-3.3-70b-versatile`,
`llama-3.1-8b-instant`, `gemini-2.5-flash`. Newer `gemini-3.5-flash` /
`gemini-3.1-flash-lite` exist and can be set via `GEMINI_MODEL` in `.env`. Free-tier limits change often — re-verify if picking this up
after a gap.

---

## How to validate the pipeline

Five layers, cheapest first. Run them in order — each builds confidence before
the next.

**1. Unit tests (no keys, no models, seconds).** Logic of the chunker, RRF
fusion, BM25 metadata filter, router JSON parsing, pydantic contracts, and the
feedback store:
```bash
pytest tests/ -v          # expect 18 passing
```

**2. Retrieval eval (no LLM keys; needs the vector store).** A fixed set of 16
test queries, each with a known-correct RITA chapter; asserts the right chapter
appears in the top-3 reranked results and prints a pass rate:
```bash
python scripts/check_vector_store.py     # confirm KB is built first
python scripts/eval_retrieval.py         # target: ≳70% top-3 chapter hit-rate
python scripts/eval_retrieval.py --no-filter   # ablation: shows the lift the
                                               # knowledge_area pre-filter gives
```
If the pass rate is low, retrieval (chunking/tagging/embedding) needs tuning
*before* trusting anything the agents produce on top of it.

**3. Full agent pipeline with real keys (synthetic KB, ~1–2 min, ~15 LLM calls).**
Exercises the router (incl. Groq 429 backoff + Gemini fallback), all six agents,
the LangGraph wiring, citation grounding, and JSON serialization — end to end,
without waiting on the real book:
```bash
python scripts/_smoke_pipeline.py        # prints score, findings, cited refs,
                                         # "SMOKE TEST PASSED"
```

**4. The API itself.** With the app running (`uvicorn app.main:app`):
```bash
curl http://127.0.0.1:8000/api/status    # kb_built / keys / can_run
```
The browser UI streams each step live; watch the stepper advance through all
six nodes.

**5. Manual / governance check (the real point).** In the **Validation** tab,
spot-check that each finding's citation chip (“📖 RITA Ch.X, p.Y”) actually
points at the right knowledge area, and that gaps/risks are reasonable for the
SOW. Citations are mapped from real retrieved-chunk metadata, not generated by
the LLM — so a wrong citation means a retrieval/tagging problem, not a
hallucination. Capture feedback, then confirm it appears in the **Feedback
dashboard** aggregates.

## Demo script (for a PMO manager)

1. `uvicorn app.main:app` → open http://127.0.0.1:8000. The sidebar shows
   system status (knowledge base ✅, LLM key ✅).
2. The SOW box is pre-filled with a sample CRM-migration SOW. Click
   **▶ Run pipeline** and watch the 5 stages light up in the live stepper.
3. Open the **3 · Validation** tab: read the **PMO Compliance Score**, the
   per-section scores, and expand a finding to see the **citations panel**
   ("📖 RITA Ch.X, p.Y"). This is the governance/traceability story.
4. **4 · Gaps/Risks & Recs**: severity-ranked gaps/risks (note Ch.14 common
   pitfalls referenced) and prioritized, cited recommendations.
5. **5 · Optimized Plan**: executive summary + the diff vs. the draft +
   the compliance score.
6. Submit **Feedback** (rating + comment), then open the **Feedback
   dashboard** to see aggregates (most-flagged gap areas, avg rating).
7. Try your own SOW: paste a real project brief and re-run.

---

## Repo layout

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Key entry points: `scripts/` (build + eval),
`src/pmo_engine/` (retrieval, llm, agents), `app/streamlit_app.py`.

---

## POC limitations

- Single knowledge source (RITA); the ingestion pipeline is generic so internal
  governance docs can be added later without redesign.
- No auth / multi-tenant storage — it's a single-user demo.
- Feedback is captured but not used to retrain (Phase 2).
- Free-tier LLM rate limits apply; the router does Groq→Gemini fallback with
  exponential backoff, but very large SOWs may still hit daily caps.
