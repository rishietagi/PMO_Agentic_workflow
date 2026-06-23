"""Show the knowledge-base build progress at a glance (multi-book aware).

Reports each source book's state (ingested? in the vector store?) and whether
the slow RITA OCR is still running. marker OCR writes nothing until it finishes
the whole book, so during OCR this shows elapsed time + a liveness signal.

    python scripts/build_status.py            # one-shot snapshot
    python scripts/build_status.py --watch     # refresh every 20s until OCR done
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pmo_engine import config  # noqa: E402

RITA_JSON = config.PROCESSED_DIR / "rita_structured.json"
PMBOK_JSON = config.PROCESSED_DIR / "pmbok_structured.json"
RITA_LOG = config.PROCESSED_DIR / "_rita_ocr.log"
FINISH_LOG = config.PROCESSED_DIR / "_finish.log"


def _proc_alive(name: str) -> bool:
    try:
        import subprocess
        out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
        return name.lower() in out.lower()
    except Exception:  # noqa: BLE001
        return False


def _ocr_start() -> datetime | None:
    for log in (RITA_LOG, FINISH_LOG):
        if not log.exists():
            continue
        for line in log.read_text(errors="ignore").splitlines():
            if "Running marker OCR" in line or ("RUN:" in line and "ingest_book" in line):
                m = re.match(r"([\d\-]+ [\d:]+)", line)
                if m:
                    try:
                        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    except Exception:  # noqa: BLE001
                        return None
    return None


def snapshot() -> dict:
    from pmo_engine.retrieval.vector_store import VectorStore
    per_book: Counter = Counter()
    try:
        vs = VectorStore()
        if vs.count():
            data = vs.collection.get(include=["metadatas"])
            for m in data.get("metadatas", []) or []:
                per_book[m.get("knowledge_base", "?")] += 1
    except Exception:  # noqa: BLE001
        pass
    return {
        "rita_ocr_done": RITA_JSON.exists(),
        "pmbok_done": PMBOK_JSON.exists(),
        "marker_alive": _proc_alive("marker_single"),
        "per_book": dict(per_book),
        "total": sum(per_book.values()),
        "ocr_start": _ocr_start(),
    }


def render(s: dict) -> str:
    o = ["=" * 62,
         "  PMO Intelligence - knowledge-base build status",
         "=" * 62]
    pb = s["per_book"]
    o.append("  Vector store (live, used by the app):")
    if pb:
        for kb, n in sorted(pb.items()):
            o.append(f"     - {config.kb_abbrev(kb):6} {n:>5} chunks  ({kb})")
        o.append(f"     total: {s['total']} chunks")
    else:
        o.append("     (empty - not built yet)")
    o.append("-" * 62)

    # PMBOK
    o.append(f"  PMBOK (text, no OCR)   {'DONE' if s['pmbok_done'] else 'pending'}"
             f"{'  - in vector store' if 'PMBOK_Guide_6th' in pb else ''}")

    # RITA OCR
    if s["rita_ocr_done"]:
        in_store = "RITA_10th_Edition" in pb
        o.append(f"  RITA (scanned, OCR)    OCR DONE"
                 f"{'  - in vector store' if in_store else '  - run combined build'}")
        if not in_store:
            o.append("       NEXT: stop the app, then  "
                     "python scripts/build_vector_store.py --rebuild")
    elif s["marker_alive"]:
        el = ""
        if s["ocr_start"]:
            el = f" - elapsed {int((datetime.now()-s['ocr_start']).total_seconds()/60)} min"
        o.append(f"  RITA (scanned, OCR)    IN PROGRESS - running{el}")
        o.append("       (CPU OCR of 551 scanned pages is slow; 4GB GPU is too "
                 "small to accelerate it)")
    else:
        o.append("  RITA (scanned, OCR)    NOT LOADED (optional)")
        o.append("       OCR of the 551-page scan is impractical here (CPU ~12h+,")
        o.append("       4GB GPU thrashes). To add later: run ingest_book.py on")
        o.append("       capable hardware, then build_vector_store.py --rebuild.")
    o.append("-" * 62)
    both = ("RITA_10th_Edition" in pb) and ("PMBOK_Guide_6th" in pb)
    if both:
        o.append("  STATUS: [BOTH BOOKS LIVE]")
    elif "PMBOK_Guide_6th" in pb and s["marker_alive"]:
        o.append("  STATUS: [PMBOK live; RITA OCR running]")
    elif "PMBOK_Guide_6th" in pb:
        o.append("  STATUS: [PMBOK live - active knowledge base; RITA optional]")
    elif pb:
        o.append("  STATUS: [partial]")
    else:
        o.append("  STATUS: [empty - build the KB]")
    o.append("=" * 62)
    return "\n".join(o)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true")
    args = ap.parse_args()
    while True:
        s = snapshot()
        print("\n" + render(s))
        done = s["rita_ocr_done"] and "RITA_10th_Edition" in s["per_book"]
        if not args.watch or done:
            return 0
        time.sleep(20)


if __name__ == "__main__":
    raise SystemExit(main())
