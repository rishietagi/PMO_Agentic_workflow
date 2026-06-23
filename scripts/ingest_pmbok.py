"""Ingest the PMBOK Guide (6th Ed.) — text-layer extraction (no OCR needed).

PMBOK is a digital PDF, so this is fast and CPU-only for extraction; the GPU is
used later by build_vector_store.py for embeddings. Produces
data/processed/pmbok_structured.json, which the multi-book
build_vector_store.py picks up alongside RITA.

    python scripts/ingest_pmbok.py
    python scripts/ingest_pmbok.py --rebuild
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pmo_engine import config  # noqa: E402
from pmo_engine.ocr import extract_structure as es  # noqa: E402
from pmo_engine.ocr.extract_text import extract_structured  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest_pmbok")

STRUCTURED_JSON = config.PROCESSED_DIR / "pmbok_structured.json"
MARKDOWN_OUT = config.PROCESSED_DIR / "pmbok.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(config.PMBOK_PDF_PATH))
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        logger.error("PMBOK PDF not found: %s", pdf)
        return 2
    if STRUCTURED_JSON.exists() and not args.rebuild:
        logger.info("%s exists — skipping (pass --rebuild to re-extract).",
                    STRUCTURED_JSON.name)
        return 0

    elements = extract_structured(pdf)
    if not elements:
        logger.error("No elements extracted from PMBOK.")
        return 1
    es.save_elements(elements, STRUCTURED_JSON, MARKDOWN_OUT)

    headings = [e for e in elements if e.heading_level]
    logger.info("PMBOK ingest complete: %d elements, %d headings, pages %s..%s",
                len(elements), len(headings), elements[0].page, elements[-1].page)
    logger.info("Heading levels: %s",
                dict(Counter(e.heading_level for e in headings)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
