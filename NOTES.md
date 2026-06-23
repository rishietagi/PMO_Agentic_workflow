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
