# Architecture — PMO Intelligence Engine

Precise reference for how the system is wired. For *why* decisions were made,
see [TECH_STACK.md](TECH_STACK.md); for product scope see
[PROJECT.md](PROJECT.md).

---

## 1. High-level shape

```
                          ┌──────────────────────────────────────────┐
   Browser (React SPA)    │              FastAPI (app/main.py)         │
   Vite · Tailwind ·  ───▶│  /api/upload-sow (PDF→text)  /api/run (NDJSON)│
   shadcn/ui · Recharts   │  /api/status /api/feedback /api/dashboard /SPA│
                          └───────────────┬────────────────────────────┘
                                          │ constructs once (lazy)
                                          ▼
                                 PMOEngine (LangGraph)
                                          │
        ┌─────────────────────────────────┼───────────────────────────────┐
        ▼                                 ▼                                 ▼
   LLM Router                      6 Agents (nodes)                 Hybrid Retriever
 (Groq ↔ Gemini)            intake→plan→validate→gap_risk        dense(BGE)+sparse(BM25)
 cheap/reason routing       →recommend→finalize (+loop)          RRF → rerank → parent
 backoff + fallback                  │                                    │
                                     ▼                                    ▼
                            Pydantic state objects              ChromaDB + BM25 + parent
                                     │                          store (built from RITA OCR)
                                     ▼
                            SQLite feedback store
```

Single runtime process: `uvicorn app.main:app`. The React app is a static
build (`app/spa/`) served by the same FastAPI server; there is no separate
Node server at runtime.

---

## 2. Two pipelines

### 2a. Offline: knowledge-base build (multi-book, run once)
```
Per book (config.KNOWLEDGE_BASES registry):
  RITA  (scanned)  → scripts/ingest_book.py  → marker OCR (CPU)
                     → ocr/extract_structure.py → StructuredElement[] (rita_structured.json)
  PMBOK (digital)  → scripts/ingest_pmbok.py → ocr/extract_text.py (PyMuPDF, no OCR)
                     → StructuredElement[] (pmbok_structured.json)

scripts/build_vector_store.py  (combines ALL ingested books into ONE store)
  for each book: chunking/hierarchical_chunker.py(chapter_map, knowledge_base)
                 → Chunk[] (id-prefixed per book) + parent sections
                 + per-(book,chapter) LLM chapter summaries
  ├─ embed (BAAI/bge-base-en-v1.5, GPU when available) → ChromaDB (one collection)
  ├─ BM25 (rank_bm25) over the union                   → data/bm25_index.pkl
  └─ parent sections                                    → data/parent_store.json

scripts/eval_retrieval.py   (sanity gate; 94% top-3 chapter hit-rate on PMBOK)
```
Each chunk carries `knowledge_base` metadata; retrieval spans the union and
citations name the source book (RITA / PMBOK). `_finish_build.py` orchestrates
RITA-OCR → PMBOK → combined build → eval unattended. `build_status.py` reports
per-book state; `check_vector_store.py` reports overall build state. Idempotent
(`--rebuild` forces). Adding a third book = add a registry entry + an ingest
step; no redesign.

### 2b. Online: the agent pipeline (per request)
A **LangGraph** state graph (`agents/graph.py`) over a single `PipelineState`
(`agents/state.py`). Nodes and their typed outputs:

| # | Node (agent) | Reads | Produces | LLM tier |
|---|---|---|---|---|
| 1 | `intake` | raw SOW | `ProjectInput` | cheap (8B) |
| 2 | `plan_generation` | ProjectInput | `DraftPlan` (10 KA sections) | reasoning (70B) |
| 3 | `validation` | DraftPlan | `ValidationReport` (scores, cited findings) | cheap (sub-queries) + reasoning (synthesis) |
| 4 | `gap_risk` | DraftPlan, ValidationReport | `RiskGapList` | reasoning |
| 5 | `recommendations` | report, risks | `Recommendations` | reasoning |
| 6 | `finalization` | plan, report, recs | `OptimizedPlan` | reasoning |

Edges: `intake → plan_generation → validation → gap_risk → recommendations →
finalization`. **Feedback-loop edge:** a conditional edge from `finalization`
routes back to `validation` (feeding the optimized plan in as the new draft)
when `compliance < 60` and `iteration < max_iterations`; otherwise to `END`.
`recursion_limit=25` bounds the loop.

---

## 3. The validation engine (core differentiator) — per plan section

```
section (knowledge_area=Scope)
  1. sub-queries        LLM (8B) → 2–4 targeted retrieval queries
  2. metadata filter    Chroma where{knowledge_area=Scope}   ← before search
  3. hybrid retrieve    dense (BGE cosine) + sparse (BM25)
  4. RRF fuse           reciprocal rank fusion (k=60)
  5. rerank             cross-encoder/ms-marco-MiniLM-L-6-v2 → top 5
  6. parent expand      small chunk → full parent section text
  7. synthesize         LLM (70B): score 0–100 + findings, each tagged with
                        evidence ids → citations mapped from REAL chunk metadata
```
Citations (`chapter`, `section_path`, `page_start/end`) are taken from the
retrieved chunk's metadata, never produced by the LLM — so a bad citation
indicates a retrieval/tagging issue, not a hallucination. Overall compliance =
mean of section scores. An optional Gemini "second opinion" cross-checks the
overall score.

---

## 4. Request lifecycle: `POST /api/run`

1. Browser `fetch("/api/run", {sow, second_opinion, max_iterations})`.
2. FastAPI returns a `StreamingResponse` of **NDJSON** lines; the sync
   generator runs in a threadpool so blocking LLM/retrieval calls don't stall
   the event loop.
3. For each LangGraph node completion → `{"type":"progress","node":...}`.
4. Final → `{"type":"result","state": <serialized PipelineState>}`; errors →
   `{"type":"error","message":...}`.
5. The React client reads the stream incrementally, advances the stepper, then
   renders results (gauge, charts, finding/citation cards).

---

## 5. LLM routing (`llm/router.py`)

- `TaskTier.CHEAP` → Groq `llama-3.1-8b-instant` (intake, sub-queries,
  classification). `TaskTier.REASONING` → Groq `llama-3.3-70b-versatile`
  (validation synthesis, recommendations, finalization).
- Groq primary with exponential backoff + jitter on 429; on exhaustion/error
  → **Gemini `gemini-2.5-flash`** fallback.
- `complete_json()` tolerates fenced/loose JSON. No agent calls a provider SDK
  directly — routing/fallback stay centralized.

---

## 6. Retrieval components (`retrieval/`)

| Module | Role |
|---|---|
| `vector_store.py` | ChromaDB wrapper + local BGE embeddings (lazy singleton) |
| `bm25_index.py` | rank_bm25 sparse index + Chroma-style metadata matcher; pickled |
| `reranker.py` | cross-encoder reranker (lazy; degrades to fused order on failure) |
| `hybrid_retriever.py` | KA pre-filter → dense+sparse → RRF → rerank → parent expand; multi-query dedupe; open-search fallback if a filter returns empty |

---

## 7. State & persistence

- **In-flight state:** `PipelineState` (pydantic) carried through the graph;
  all cross-agent objects are pydantic models (`ProjectInput`, `DraftPlan`,
  `ValidationReport`, `RiskGapList`, `Recommendations`, `OptimizedPlan`).
- **Knowledge base:** `data/chroma_db/` (vectors+metadata), `data/bm25_index.pkl`,
  `data/parent_store.json`.
- **Feedback:** `data/feedback.db` (SQLite) — `feedback` and `gap_events`
  tables; aggregates surfaced in the dashboard. Instrumentation only.

---

## 8. Chunk metadata schema (drives filtered retrieval + citations)

`chapter_number, chapter_title, knowledge_area, section_path, page_start,
page_end, content_type, process_group, knowledge_base[, summary_method]`.
`content_type ∈ {itto, formula, definition, exam_tip, common_pitfall, concept,
chapter_summary, endnote}`. `knowledge_area` for Ch.5–13 maps ~1:1 to plan
sections — the primary precision lever.

---

## 9. Frontend structure (`frontend/src/`)

- `App.jsx` — layout shell (Sidebar + view switch: Run / Dashboard).
- `components/RunView.jsx` — SOW input, options, NDJSON run + live `Stepper`.
- `components/ResultsView.jsx` — tabs (Initiation/Plan/Validation/Gaps·Recs/
  Optimized), hero gauge, charts, `FindingCard`s with citation chips.
- `components/Dashboard.jsx` — feedback metrics + charts.
- `components/Charts.jsx` — Recharts (radial gauge, section bars, breakdown pie).
- `components/ui/*` — shadcn/ui primitives (button, card, tabs, badge, progress,
  textarea, switch, select, separator).
- `lib/api.js` — fetch + NDJSON stream reader. `lib/utils.js` — `cn`, score color.
