"""Unattended finisher: model-load -> book OCR -> vector store -> eval.

Runs the remaining runtime steps as one resilient background chain so the build
completes without supervision once the (slow, throttled) marker model download
finishes. Each step is idempotent and skipped if already done.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PY = sys.executable

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s finisher: %(message)s")
log = logging.getLogger("finisher")


def step(cmd: list[str]) -> int:
    log.info("RUN: %s", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(ROOT))
    log.info("exit %s", r.returncode)
    return r.returncode


def wait_for_models(max_minutes: int = 600) -> bool:
    """Retry create_model_dict until the cache is complete (resumes downloads)."""
    deadline = time.time() + max_minutes * 60
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            from marker.models import create_model_dict
            t = time.time()
            create_model_dict()
            log.info("marker models ready (attempt %d, %.1fs)", attempt,
                     time.time() - t)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("model load attempt %d failed: %s; retry in 10s",
                        attempt, exc)
            time.sleep(10)
    return False


def main() -> int:
    from pmo_engine import config
    from pmo_engine.retrieval.vector_store import VectorStore

    # 0) models
    if not wait_for_models():
        log.error("models never finished downloading; aborting.")
        return 1

    # 1a) RITA OCR (marker, GPU when available) — skip if structured json exists
    rita = config.PROCESSED_DIR / "rita_structured.json"
    if rita.exists():
        log.info("RITA structured JSON present; skipping OCR.")
    else:
        if step([PY, "scripts/ingest_book.py",
                 "--pdf", str(config.DEFAULT_PDF_PATH)]) != 0:
            log.error("RITA ingestion failed."); return 2

    # 1b) PMBOK text extraction (no OCR) — skip if present
    pmbok = config.PROCESSED_DIR / "pmbok_structured.json"
    if pmbok.exists():
        log.info("PMBOK structured JSON present; skipping extraction.")
    elif config.PMBOK_PDF_PATH.exists():
        if step([PY, "scripts/ingest_pmbok.py"]) != 0:
            log.error("PMBOK ingestion failed (continuing with RITA only).")
    else:
        log.info("PMBOK PDF not found; building RITA only.")

    # 2) combined vector store — always --rebuild so the real books overwrite
    #    any demo/synthetic placeholder store that may have been seeded.
    if step([PY, "scripts/build_vector_store.py", "--rebuild"]) != 0:
        log.error("vector store build failed."); return 3

    # 3) retrieval eval (no LLM needed)
    step([PY, "scripts/eval_retrieval.py"])
    log.info("FINISHER COMPLETE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
