# Build Notes — PMO Intelligence Engine

Running log of decisions made during the autonomous build, with reasoning.
Newest entries at the bottom of each phase.

## Phase 0 — Environment

- **Conda env did not exist** at build start (`conda env list` showed no
  `pmo-intel-engine`). This is a first-ever setup, so creating it is correct
  per CLAUDE.md §2 rule 3. On future sessions it must NOT be recreated.
- **PDF filename mismatch.** CLAUDE.md references `RITA_10th_Edition.pdf`,
  but the actual file is `data/raw/RITA 10th Edition.pdf` (spaces, no
  underscores). Decision: `scripts/ingest_book.py` defaults to the real
  filename and also accepts `--pdf`. Did not rename the file to avoid
  breaking any external reference the user has.
- **Removed stray empty `hi.py`** from repo root (scaffolding leftover).
- **Model IDs verified against live docs (2026-06-21):**
  - Groq: `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` both still
    available as production models. Keeping both as specified.
  - Gemini: `gemini-2.5-flash` still stable (CLAUDE.md's documented "safe
    default"). DRIFT NOTE: newer `gemini-3.5-flash` (stable) and
    `gemini-3.1-flash-lite` (stable) now exist. Free-tier eligibility of 3.5
    not confirmed from public docs, so default stays `gemini-2.5-flash` but
    is overridable via `GEMINI_MODEL` env var. Flagging per CLAUDE.md §2
    rule 6 / §4.
- **Google SDK:** using `google-genai` (the current unified GenAI SDK,
  `from google import genai`), NOT the deprecated `google-generativeai`.
- **System Tesseract binary** is an external dependency for the
  `pytesseract` OCR fallback. The fallback degrades gracefully (logs a
  warning and skips) if the binary isn't installed, since marker-pdf is the
  primary path and Tesseract is only the per-page fallback.

## Phase 1 — Book ingestion

- **PDF confirmed image-based.** PyMuPDF on page 100: 0 chars of text, 3
  images. 551 pages total. Matches CLAUDE.md — OCR is mandatory.
- **`conda run` buffers all subprocess stdout until exit** — this made marker
  appear hung (0-byte logs, idle CPU) on the first two attempts. Fix: invoke
  the env python directly (`C:\miniconda\envs\pmo-intel-engine\python.exe -u`)
  instead of `conda run`. All long-running/streamed commands now use the
  direct exe. (The conda env itself is correct and untouched.)
- **marker model location:** surya/marker models download to
  `%LOCALAPPDATA%\datalab\...`, NOT the HF hub cache — initial confusion when
  the HF cache wasn't growing.
- **marker model download throttling (network).** The text_recognition
  safetensors (1.34 GB) throttled to ~50 kB/s (multi-hour ETA) on the default
  downloader. Installed `hf_transfer` and set `HF_HUB_ENABLE_HF_TRANSFER=1`,
  which restored ~9.5 MB/s. `hf_transfer` is a download accelerator, not a
  stack dependency — added pragmatically to unblock; noted here. Total marker
  models ~3-4 GB; one-time.
- Implemented `extract_structure.py` to drive marker via JSON output (richer
  than markdown: per-block types + page numbers for citations) and normalize
  to an ordered `StructuredElement` list; also renders a `rita.md` for human
  spot-checking. Tables/Equations are kept atomic; Index/headers/footers
  skipped at the parser level. PyMuPDF+Tesseract per-page fallback implemented
  and degrades gracefully if Tesseract isn't installed.

## Phase 2 — Chunking + vector store

(to be filled in)

## Phase 3 — Retrieval

(to be filled in)

## Phase 4 — LLM routing

(to be filled in)

## Phase 5 — Agents

(to be filled in)

## Phase 6 — UI + docs

- **UI changed from Streamlit → FastAPI + Uvicorn** per explicit user
  direction (2026-06-21): "do not use streamlit ... Use a FastAPI based
  frontend connected with Uvicorn, make it look beautiful." Updated CLAUDE.md
  tech stack + repo layout in the same turn (per CLAUDE.md's own override
  rule), environment.yml (added fastapi/uvicorn/jinja2/python-multipart,
  removed streamlit), and README.
- Implementation: `app/main.py` (FastAPI) serves a Jinja2 single-page app
  (`app/templates/index.html` + `app/static/{style.css,app.js}`). The
  `/api/run` endpoint streams **NDJSON** (one progress event per LangGraph
  node, then a final serialized-state event) so the UI shows a live stepper.
  Sync generator in StreamingResponse → FastAPI runs it in a threadpool so the
  blocking LLM/retrieval work doesn't stall the event loop. Endpoints:
  `/api/status`, `/api/run`, `/api/feedback`, `/api/dashboard`,
  `/api/sample-sow`. Design: dark theme, SVG compliance gauge (color-coded by
  score), per-section score bars, collapsible finding cards with citation
  chips, feedback stars, and a dashboard with gap-area bars.
- Removed the old `app/streamlit_app.py`.

## Phase 1/2/3 runtime status

- Marker model download remained the bottleneck (one ~201 MB surya model file
  throttled to ~20 kB/s server-side even with hf_transfer; surya re-downloads
  this file from zero on each restart, so it must run uninterrupted). Left it
  grinding in the background.
- **De-risked Phase 5 independently:** validated the full agent pipeline
  (router → all 6 agents → LangGraph → citation grounding → JSON
  serialization) end-to-end against a small synthetic vector store using the
  real Groq/Gemini keys, so the only thing the real book OCR changes is the
  knowledge-base content, not any code path. See `scripts/_smoke_pipeline.py`.

## Retrieval quality upgrade — Tier 1 + Tier 2 (2026-06-23)

GPU-accelerated retrieval improvements (PMBOK active KB). Measured with the new
`scripts/eval_retrieval.py --detailed` (MRR + keyword-hit@1/@5) over 28 queries
incl. indirectly-worded ones; the sensitive comparison is **no knowledge-area
filter**:

| metric (no-filter, n=28) | baseline (bge-base) | after |
|---|---|---|
| chapter@5 | 96% | 100% |
| chapter-MRR | 0.927 | 0.948 |
| keyword-hit@1 | 89% | 93% |
| keyword-MRR | 0.921 | 0.943 |
| keyword-hit@5 | 100% | 96% |

NOTE: with the KA pre-filter on (the app's normal path) retrieval was already
~saturated (≈100%) on realistic single-book queries, so the headroom is in the
hard / no-filter regime and in correctness (below).

Changes:
- **Tier 2.1 models (GPU, fp16):** embeddings bge-base → **bge-large-en-v1.5**;
  reranker MiniLM-L-6 → **bge-reranker-v2-m3** (fallback bge-reranker-base →
  MiniLM). Peak VRAM 3.46 GB of 4 GB. `config.use_fp16()`.
- **Tier 1.3 contextual retrieval:** each chunk embedded/BM25-indexed with a
  breadcrumb prefix `[BOOK | KnowledgeArea | section]`; stored/displayed text
  stays clean (`Chunk.embed_text()`; `VectorStore.add(embed_texts=)`,
  `BM25Index.build(embed_texts=)`).
- **Tier 1.1 PMBOK extraction:** forward-only chapter logic (a backward "5.x"
  while deep in ch.11 is treated as a cross-reference, not a heading → fixes the
  p.608-type mis-tags) + **Part 2 / back-matter cutoff after ch.13** (removes
  the Standard's duplication). Chunk count **996 → 543**.
- **Tier 1.2 overlap:** sentence-aware, token-based overlap applied consistently
  (replaces word-tail-on-big-sections-only).
- **Tier 2.2 ITTO tagging:** title-based detection of Inputs / Tools and
  Techniques / Outputs subsections → **302 `itto` chunks** (was 0), restoring
  structured signal to the validation + Gap/Risk agents.
- Eval harness gained `--detailed` (MRR, keyword-hit@1/@5) and adaptive
  chapter-skipping for whatever books are loaded.
- Deferred (low ROI): image-table OCR extraction — PMBOK ITTO are text lists
  already captured by 2.2.
