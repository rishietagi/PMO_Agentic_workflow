# Tech Stack — PMO Intelligence Engine

Every technology in the system: what it is, the version/model used, why it was
chosen, and how it's used here.

---

## Runtime & environment

| Tech | Version | Why | How used |
|---|---|---|---|
| Python | 3.11 | Modern typing; broad ML lib support | All backend, agents, RAG, scripts |
| Conda | env `pmo-intel-engine` | Reproducible, isolates heavy ML deps | The **only** env; never recreated once built (project operating rules) |
| Node.js | ≥20 (26.3 installed) | Required to build the React/shadcn SPA | Build-time only (Vite); not a runtime server |
| PyTorch | 2.12.1+cu126 (CUDA) | GPU acceleration for embeddings/reranking | `config.resolve_device()` → `cuda` when available, else `cpu` |
| GPU | NVIDIA (dev: RTX 3050, **4 GB**) | Faster embeddings/vectors at build + query time | Embeddings + reranker run on GPU; **OCR stays on CPU** — 4 GB is too small for marker's 5–6 simultaneous surya models (proven to thrash). Override per-process via `PMO_DEVICE`/`TORCH_DEVICE`. |

---

## Knowledge-base ingestion (offline, one-time)

| Tech | Version/Model | Why | How used |
|---|---|---|---|
| marker-pdf | latest | RITA is a **scanned** PDF (no text layer); marker does layout-aware OCR and emits a structured block tree with headings/tables/equations | `scripts/ingest_book.py` → JSON block tree (CPU) |
| PyMuPDF (fitz) | latest | RITA: page render for OCR fallback. **PMBOK: full text extraction** — it's a digital PDF, so no OCR | `scripts/ingest_pmbok.py` → structure recovered from PMBOK section numbering ("5.1 …"); much faster than OCR |
| pytesseract + Pillow | latest | Per-page OCR fallback for pages marker mangles | `ocr/extract_structure.ocr_page_fallback` (degrades gracefully if Tesseract absent) |
| tiktoken | latest | `cl100k_base` as a token-length heuristic | Chunk sizing (~300–600 tokens) |
| hf_xet, hf_transfer | latest | Accelerate/robustify HF model downloads (Xet-backed repos were the real throttle) | Env vars during model fetch |

---

## Retrieval / RAG (local, no API at query time)

| Tech | Version/Model | Why | How used |
|---|---|---|---|
| sentence-transformers | latest | Local embeddings + reranking; no rate limits at demo time | Loads BGE + cross-encoder |
| Embeddings | **BAAI/bge-large-en-v1.5** (fp16 GPU) | Stronger retrieval than bge-base; fp16 fits 4 GB | Dense vectors for Chroma; **breadcrumb-prefixed** text embedded (contextual retrieval); query prefix applied |
| Reranker | **BAAI/bge-reranker-v2-m3** (fp16 GPU; falls back to bge-reranker-base → MiniLM) | Much stronger cross-encoder than MiniLM | Rerank fused top-20 → top 5 |
| ChromaDB | latest | Zero-infra persisted vector store with metadata filtering | `data/chroma_db/`; KA pre-filter before search |
| rank_bm25 | latest | Exact-match for PM acronyms (WBS, EVM, RACI, ITTO) that embeddings miss | Sparse index; pickled to `data/bm25_index.pkl` |
| Fusion | Reciprocal Rank Fusion (k=60) | Rank-based, no hand-tuned weights | Combine dense + sparse rankings |
| Parent store | JSON | Small-to-big retrieval: search precise chunks, expand to full section for the LLM | `data/parent_store.json` keyed by `section_path` |

---

## LLMs

| Tech | Model ID | Tier / role | Notes |
|---|---|---|---|
| Groq | `llama-3.1-8b-instant` | CHEAP — intake, sub-query gen, classification | High daily cap (~14.4k/day); fast |
| Groq | `llama-3.3-70b-versatile` | REASONING — validation synthesis, gap/risk, recs, finalize | Tighter cap (~1k/day) → reserved for reasoning |
| Google Gemini | `gemini-2.5-flash` | Fallback on Groq 429/error; optional 2nd-opinion on score | Free tier = Flash/Flash-Lite only (2026); override via `GEMINI_MODEL` |
| google-genai | latest | Current unified Google SDK (`from google import genai`) | Not the deprecated `google-generativeai` |
| groq | latest | Groq SDK | Wrapped; only the router imports it |

Routing/fallback/backoff centralized in `llm/router.py`; agents never call a
provider SDK directly. Model IDs verified live 2026-06-21;
re-verify after gaps — free-tier names/limits drift.

---

## Orchestration & data contracts

| Tech | Version | Why | How used |
|---|---|---|---|
| LangGraph | latest | First-class conditional branching + the feedback-loop edge (steps 7–8), vs. a flattened chain | `agents/graph.py` state graph over `PipelineState` |
| Pydantic | v2 | Typed contracts at every agent boundary; safe JSON serialization to the UI | All cross-agent objects (`agents/state.py`) |

---

## Web backend

| Tech | Version | Why | How used |
|---|---|---|---|
| FastAPI | 0.138 | Async API + native streaming; serves the built SPA | `app/main.py`: `/api/status,/run,/upload-sow,/feedback,/dashboard,/sample-sow`, `/` |
| Uvicorn | latest (`[standard]`) | ASGI server | `uvicorn app.main:app` |
| NDJSON over StreamingResponse | — | Stream per-step progress to the browser without WebSockets; sync generator runs in a threadpool | `/api/run` |
| SQLite (stdlib) | — | Enough for POC feedback capture | `data/feedback.db` (`feedback`, `gap_events`) |

---

## Frontend (React SPA, built by Vite, served by FastAPI)

| Tech | Version | Why | How used |
|---|---|---|---|
| React | 18 | Component model for a polished, stateful SPA | `frontend/src/` (JSX, no TS to avoid build-time type breakage) |
| Vite | 6 | Fast build; outputs static `app/spa/` | `npm run build`; dev proxy to uvicorn on :5173 |
| Tailwind CSS | 3.4 | Utility styling; design tokens via CSS vars | `tailwind.config.js`, `src/index.css` |
| shadcn/ui pattern | Radix + CVA | Accessible, themeable primitives (vendored as source, not via CLI) | `components/ui/*` (button, card, tabs, badge, progress, textarea, switch, select, separator) |
| Radix UI | latest | Headless a11y primitives behind shadcn components | tabs, switch, progress, select, slot, separator |
| Recharts | 2.15 | Analytics charts | Compliance gauge + rings, KA radar, KA compliance heatmap, likelihood×impact risk matrix, concentration treemap, donuts, KPI tiles (`lib/analytics.js`) |
| lucide-react | latest | Icon set | Throughout the UI |
| framer-motion | latest | Entrance/stagger animations | Executive dashboard + step intros |
| class-variance-authority, clsx, tailwind-merge | latest | Variant + class composition (the `cn` helper) | `lib/utils.js`, component variants |

---

## Testing & tooling

| Tech | Why | How used |
|---|---|---|
| pytest | Unit tests without keys/models | `tests/test_core.py` (18 tests): chunker, RRF, BM25 matcher, router JSON, pydantic, feedback store |
| `scripts/eval_retrieval.py` | Retrieval sanity gate (no LLM) | 16 fixed queries → expected chapter in top-3 |
| `scripts/_smoke_pipeline.py` | Full pipeline integration with real keys on a synthetic KB | Validates router/agents/graph/citations/serialization |
| python-dotenv | Load secrets from `.env` (gitignored) | `config.py` |

---

## What is intentionally NOT used

- **Streamlit** — replaced by FastAPI + React per user direction.
- **OpenAI / LangChain LLM wrappers** — direct Groq/Gemini SDKs behind a thin
  router keep prompts debuggable.
- **A separate Node runtime server** — the SPA is a static build served by
  FastAPI; Node is build-time only.
- **Cloud vector DB / managed infra** — ChromaDB local file store; POC runs
  entirely inside the conda env.
