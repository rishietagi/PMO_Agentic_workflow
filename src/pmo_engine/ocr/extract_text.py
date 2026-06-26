"""Text-layer extraction for digital PDFs (e.g. PMBOK Guide 6th).

PMBOK ships as a digital PDF with a real text layer but NO bookmarks/TOC, so we
recover structure from its consistent section numbering ("5  PROJECT SCOPE
MANAGEMENT", "5.1 Plan Scope Management", "5.1.1 ..."). Section numbers reveal
the chapter (and thus knowledge area) even when the chapter title page is
sparse. Emits the same `StructuredElement` list the marker path produces, so
the one hierarchical chunker handles both books unchanged.
"""
from __future__ import annotations

import logging
import re

from pmo_engine import config
from pmo_engine.ocr.extract_structure import StructuredElement

logger = logging.getLogger(__name__)

# "5.1 Plan Scope Management" / "5.1.1 ..." (section headings)
_SECTION_RE = re.compile(r"^(\d{1,2})\.(\d+)(?:\.(\d+))?\.?\s+([A-Z][\w].{2,70})$")
# "5  PROJECT SCOPE MANAGEMENT" (chapter heading on its own line)
_CHAPTER_RE = re.compile(r"^(\d{1,2})\s+([A-Z][A-Z &/-]{6,60})$")
# Back-matter: PMBOK Part 2 "The Standard" restates Part 1 (duplication), and
# appendices/glossary/index/references add no plan-validation value. We stop
# section ingestion here — this is the dedup + precision win.
_BACKMATTER_RE = re.compile(
    r"^(part\s*2\b|the standard for project management|appendix\b|annex\b|"
    r"glossary\b)", re.I)


def _clean(text: str) -> str:
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def extract_structured(pdf_path, chapter_map: dict | None = None
                       ) -> list[StructuredElement]:
    import fitz  # PyMuPDF

    chapter_map = chapter_map or config.PMBOK_CHAPTER_MAP
    doc = fitz.open(pdf_path)
    elements: list[StructuredElement] = []
    order = 0
    chapters_emitted: set[int] = set()
    buf: list[str] = []
    buf_page = 0

    def flush_text(page: int):
        nonlocal order, buf
        body = _clean("\n".join(buf))
        buf = []
        if len(body) >= 40:
            elements.append(StructuredElement(
                order=order, page=page, block_type="Text",
                heading_level=None, text=body))
            order += 1

    def emit_heading(page: int, level: int, text: str):
        nonlocal order
        elements.append(StructuredElement(
            order=order, page=page, block_type="SectionHeader",
            heading_level=level, text=text))
        order += 1

    def ensure_chapter(page: int, ch: int):
        """Emit a chapter heading the first time we see content from chapter ch."""
        nonlocal order
        if ch in chapters_emitted or ch not in chapter_map:
            return
        chapters_emitted.add(ch)
        flush_text(page)
        emit_heading(page, 1, chapter_map[ch]["title"])

    cur_chapter = 0
    stop = False
    for pidx in range(doc.page_count):
        if stop:
            break
        lines = doc[pidx].get_text("text").splitlines()
        for raw in lines:
            line = _clean(raw)
            if not line:
                continue
            # Stop at Part 2 / back-matter only AFTER all 13 KA chapters are
            # seen, and only on a short heading-like line (not a body sentence
            # that merely starts with "Appendix"/"The Standard…").
            if cur_chapter >= 13 and len(line) < 60 and _BACKMATTER_RE.match(line):
                flush_text(pidx)
                stop = True
                break
            m_sec = _SECTION_RE.match(line)
            m_chap = _CHAPTER_RE.match(line)
            if m_sec:
                ch = int(m_sec.group(1))
                # forward-only: accept a section's chapter only if it's the
                # current chapter or the next one — a backward jump (e.g. "5.1"
                # while deep in ch.11) is a cross-reference, not a heading.
                if ch not in chapter_map or not (
                        cur_chapter == 0 or ch == cur_chapter or ch == cur_chapter + 1):
                    buf.append(line)
                    continue
                level = 2 if m_sec.group(3) is None else 3
                ensure_chapter(pidx, ch)
                cur_chapter = max(cur_chapter, ch)
                flush_text(pidx)
                emit_heading(pidx, level, line)
            elif m_chap and int(m_chap.group(1)) in chapter_map and \
                    int(m_chap.group(1)) >= cur_chapter:
                ch = int(m_chap.group(1))
                ensure_chapter(pidx, ch)
                cur_chapter = max(cur_chapter, ch)
            else:
                buf.append(line)
        flush_text(pidx)

    logger.info("Extracted %d elements from %d pages up to chapter %d "
                "(%d chapter headings, %d section headings; back-matter "
                "stopped=%s).", len(elements), doc.page_count, cur_chapter,
                sum(1 for e in elements if e.heading_level == 1),
                sum(1 for e in elements if e.heading_level and e.heading_level > 1),
                stop)
    return elements
