"""PMO Intelligence Engine — FastAPI + Uvicorn web app.

Backend for the React + Tailwind + shadcn/ui single-page app (built by Vite
into app/spa/) that mirrors the PMO manager's 5-step user journey:
  1. Project Initiation  2. AI Plan Generation  3. PMO Validation (core
  differentiator: compliance score + citations)  4. Recommendations &
  Optimization  5. Finalization — plus feedback capture + an aggregate
  dashboard (flow steps 7-8, instrumentation only).

Run:  uvicorn app.main:app --reload     (or: python -m app.main)
Rebuild the UI after frontend changes:  cd frontend && npm run build
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pmo_engine import config  # noqa: E402
from pmo_engine.agents.state import PipelineState  # noqa: E402
from pmo_engine.feedback.feedback_store import FeedbackStore  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pmo_web")

app = FastAPI(title="PMO Intelligence Engine")

# Built SPA (Vite output). Assets are referenced as /assets/* from index.html.
SPA_DIR = ROOT / "app" / "spa"
if (SPA_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(SPA_DIR / "assets")),
              name="assets")

STEP_LABELS = {
    "start": "Initializing",
    "intake": "Project Initiation",
    "plan_generation": "AI Plan Generation",
    "validation": "PMO Validation",
    "gap_risk": "Gap & Risk Identification",
    "recommendations": "AI Recommendations",
    "finalization": "Finalization & Optimization",
}

# --- lazy singletons (heavy: loads embedding + reranker models) -------------
_engine = None
_engine_error: str | None = None


def get_engine(second_opinion: bool = False, max_iterations: int = 1):
    global _engine, _engine_error
    if _engine is None:
        from pmo_engine.agents.graph import PMOEngine
        logger.info("Constructing PMOEngine (loading models + KB)...")
        _engine = PMOEngine(second_opinion=second_opinion,
                            max_iterations=max_iterations)
    return _engine


def system_status() -> dict[str, Any]:
    from pmo_engine.retrieval.bm25_index import BM25Index
    from pmo_engine.retrieval.vector_store import VectorStore
    try:
        chunks = VectorStore().count()
    except Exception:  # noqa: BLE001
        chunks = 0
    kb_ok = chunks > 0 and BM25Index.exists() and config.PARENT_STORE_PATH.exists()
    return {
        "kb_built": kb_ok,
        "kb_chunks": chunks,
        "groq_key": config.groq_key_present(),
        "google_key": config.google_key_present(),
        "can_run": kb_ok and (config.groq_key_present() or
                              config.google_key_present()),
        "models": {
            "reasoning": config.GROQ_MODEL_LARGE,
            "cheap": config.GROQ_MODEL_SMALL,
            "fallback": config.GEMINI_MODEL,
        },
    }


# --- routes ----------------------------------------------------------------
@app.get("/")
def index():
    spa = SPA_DIR / "index.html"
    if spa.exists():
        return FileResponse(str(spa))
    return JSONResponse(
        {"error": "SPA not built. Run: cd frontend && npm run build"},
        status_code=503)


@app.get("/api/status")
def api_status():
    return system_status()


class RunRequest(BaseModel):
    sow: str
    second_opinion: bool = False
    max_iterations: int = 1


def _serialize_state(state: PipelineState) -> dict[str, Any]:
    return json.loads(state.model_dump_json())


def _run_stream(req: RunRequest) -> Iterator[str]:
    """Yield NDJSON: progress events per node, then a final result event."""
    status = system_status()
    if not status["can_run"]:
        yield json.dumps({"type": "error",
                          "message": "Knowledge base not built or no API key "
                          "configured."}) + "\n"
        return
    try:
        engine = get_engine(req.second_opinion, req.max_iterations)
    except Exception as exc:  # noqa: BLE001
        yield json.dumps({"type": "error",
                          "message": f"Engine init failed: {exc}"}) + "\n"
        return

    merged: dict[str, Any] = {"raw_sow": req.sow,
                              "max_iterations": req.max_iterations}
    idx = 0
    total = len(STEP_LABELS) - 1  # exclude 'start'
    try:
        for node_name, update in engine.stream(req.sow):
            merged.update(update)
            if node_name == "start":
                yield json.dumps({"type": "progress", "node": "start",
                                  "label": STEP_LABELS["start"], "index": 0,
                                  "total": total}) + "\n"
                continue
            idx += 1
            yield json.dumps({
                "type": "progress", "node": node_name,
                "label": STEP_LABELS.get(node_name, node_name),
                "index": idx, "total": total}) + "\n"
        state = PipelineState(**merged)
        yield json.dumps({"type": "result",
                          "state": _serialize_state(state)}) + "\n"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed")
        yield json.dumps({"type": "error", "message": str(exc)}) + "\n"


@app.post("/api/run")
def api_run(req: RunRequest):
    # Sync generator -> FastAPI runs it in a threadpool, so the blocking
    # LLM/retrieval work won't stall the event loop.
    return StreamingResponse(_run_stream(req),
                             media_type="application/x-ndjson")


class FeedbackRequest(BaseModel):
    run_id: str
    project_title: str = ""
    compliance_score: int = 0
    rating: int = 4
    helpful: bool = True
    comment: str = ""
    gap_events: list[dict[str, Any]] = []


@app.post("/api/feedback")
def api_feedback(req: FeedbackRequest):
    fs = FeedbackStore()
    fs.record_feedback(req.run_id, req.project_title, req.compliance_score,
                       req.rating, req.helpful, req.comment)
    if req.gap_events:
        fs.record_gap_events(req.run_id, req.gap_events)
    return JSONResponse({"ok": True})


@app.get("/api/dashboard")
def api_dashboard():
    return FeedbackStore().aggregate()


SAMPLE_SOW_MD = ROOT / "sample" / "AI_Future_Operating_Model_SOW.md"
SAMPLE_SOW_PDF = ROOT / "sample" / "AI_Future_Operating_Model_SOW.pdf"


def _pdf_to_text(data: bytes) -> tuple[str, int]:
    """Extract text from an uploaded PDF (digital). Returns (text, page_count)."""
    import fitz  # PyMuPDF
    doc = fitz.open(stream=data, filetype="pdf")
    parts = [doc[i].get_text("text") for i in range(doc.page_count)]
    text = "\n".join(parts).strip()
    return text, doc.page_count


@app.post("/api/upload-sow")
async def api_upload_sow(file: UploadFile = File(...)):
    """Accept a SOW/RFP PDF, extract its text for the pipeline input."""
    name = (file.filename or "document.pdf")
    if not name.lower().endswith(".pdf"):
        return JSONResponse({"error": "Please upload a PDF file."},
                            status_code=400)
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        return JSONResponse({"error": "PDF too large (max 25 MB)."},
                            status_code=400)
    try:
        text, pages = _pdf_to_text(data)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"Could not read PDF: {exc}"},
                            status_code=400)
    if len(text) < 50:
        return JSONResponse(
            {"error": "No selectable text found — this looks like a scanned "
                      "PDF. Use a digital PDF or paste the text.",
             "filename": name, "pages": pages, "chars": len(text)},
            status_code=422)
    return {"filename": name, "pages": pages, "chars": len(text), "sow": text}


@app.get("/api/sample-sow")
def api_sample_sow():
    if SAMPLE_SOW_MD.exists():
        return {"sow": SAMPLE_SOW_MD.read_text(encoding="utf-8"),
                "pdf_available": SAMPLE_SOW_PDF.exists()}
    legacy = ROOT / "data" / "sample_sow.txt"
    return {"sow": legacy.read_text(encoding="utf-8") if legacy.exists() else "",
            "pdf_available": False}


@app.get("/api/sample-sow.pdf")
def api_sample_sow_pdf():
    if SAMPLE_SOW_PDF.exists():
        return FileResponse(str(SAMPLE_SOW_PDF),
                            media_type="application/pdf",
                            filename=SAMPLE_SOW_PDF.name)
    return JSONResponse({"error": "sample PDF not found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
