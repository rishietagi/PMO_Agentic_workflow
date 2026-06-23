"""Phase 1 — Book ingestion: OCR + structure extraction.

Runs marker-pdf over the scanned RITA PDF and normalizes the result into
data/processed/rita_structured.json (consumed by the chunker) plus a
human-readable data/processed/rita.md for spot-checking.

Idempotent: if the structured JSON already exists it skips re-running marker
unless --rebuild is passed (marker on a 551-page scanned book is slow).

    python scripts/ingest_book.py --pdf "data/raw/RITA 10th Edition.pdf"
    python scripts/ingest_book.py --max-pages 40   # quick smoke test
    python scripts/ingest_book.py --rebuild
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

# make `src` importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pmo_engine import config  # noqa: E402
from pmo_engine.ocr import extract_structure as es  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest_book")

STRUCTURED_JSON = config.PROCESSED_DIR / "rita_structured.json"
MARKDOWN_OUT = config.PROCESSED_DIR / "rita.md"
MARKER_RAW_DIR = config.PROCESSED_DIR / "marker_raw"


def spot_check_report(elements: list[es.StructuredElement]) -> None:
    """Print a quick structural sanity report (Phase 1 spot-check aid)."""
    types = Counter(e.block_type for e in elements)
    pages = sorted({e.page for e in elements})
    headings = [e for e in elements if e.heading_level]
    tables = [e for e in elements if e.block_type in es._TABLE_TYPES]
    formulas = [e for e in elements if e.block_type in es._FORMULA_TYPES]

    logger.info("=== Phase 1 spot-check report ===")
    logger.info("elements: %d | pages covered: %d (%s..%s)",
                len(elements), len(pages),
                pages[0] if pages else "-", pages[-1] if pages else "-")
    logger.info("block types: %s", dict(types))
    logger.info("headings: %d | tables: %d | formulas: %d",
                len(headings), len(tables), len(formulas))
    logger.info("First 12 headings (level | page | text):")
    for h in headings[:12]:
        logger.info("  H%s p.%s | %s", h.heading_level, h.page, h.text[:70])
    if tables:
        sample = tables[len(tables) // 2]
        logger.info("Sample table (p.%s):\n%s", sample.page, sample.text[:400])
    if formulas:
        logger.info("Sample formula (p.%s): %s",
                    formulas[0].page, formulas[0].text[:120])
    logger.info("=== end report ===")
    logger.info("Eyeball %s against rasterized originals for ITTO/EVM pages.",
                MARKDOWN_OUT)


def main() -> int:
    ap = argparse.ArgumentParser(description="OCR + structure extraction")
    ap.add_argument("--pdf", default=str(config.DEFAULT_PDF_PATH))
    ap.add_argument("--max-pages", type=int, default=None,
                    help="limit pages (smoke test only)")
    ap.add_argument("--rebuild", action="store_true",
                    help="re-run marker even if structured JSON exists")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        logger.error("PDF not found: %s", pdf_path)
        return 2

    if STRUCTURED_JSON.exists() and not args.rebuild and args.max_pages is None:
        logger.info("Structured output already exists at %s — skipping marker. "
                    "Pass --rebuild to force re-OCR.", STRUCTURED_JSON)
        elements = es.load_elements(STRUCTURED_JSON)
        spot_check_report(elements)
        return 0

    logger.info("Running marker OCR on %s (this is slow for a scanned book)...",
                pdf_path.name)
    json_path = es.run_marker(pdf_path, MARKER_RAW_DIR, max_pages=args.max_pages)
    logger.info("marker JSON: %s", json_path)

    import json as _json
    with json_path.open(encoding="utf-8") as f:
        doc = _json.load(f)
    elements = es.normalize_marker_json(doc)
    if not elements:
        logger.error("No elements extracted — marker output may be empty.")
        return 1

    es.save_elements(elements, STRUCTURED_JSON, MARKDOWN_OUT)
    spot_check_report(elements)
    logger.info("Phase 1 complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
