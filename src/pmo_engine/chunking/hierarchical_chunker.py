"""Phase 2 — Hierarchical, content-type-aware chunker (CLAUDE.md §5).

Consumes the normalized StructuredElement list from Phase 1 and produces:
  * a list of `Chunk`s (the small, precisely-tagged units that get embedded),
  * a parent-section store (section_path -> full section text) for small-to-big
    retrieval expansion.

Design points (all from §5):
  1. Primary split by heading hierarchy (chapter > section > subsection), not
     fixed windows.
  2. Content-type-aware: ITTO tables and formulas stay atomic; Ch.1 tips and
     Ch.14 pitfalls are tagged for the Gap & Risk agent.
  3. Sizing ~300-600 tokens (tiktoken cl100k_base heuristic); long leaves are
     recursively split with ~15% overlap while keeping atomic blocks whole;
     tiny leaves merge up.
  4. Full required metadata per chunk (chapter_number, chapter_title,
     knowledge_area, section_path, page_start/end, content_type, process_group).
  5. Index excluded, Endnotes deprioritized.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from pmo_engine import config
from pmo_engine.ocr.extract_structure import (StructuredElement, _FORMULA_TYPES,
                                              _TABLE_TYPES)

logger = logging.getLogger(__name__)

# --- token counting --------------------------------------------------------
try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text))
except Exception:  # noqa: BLE001 - tiktoken optional at import time
    def count_tokens(text: str) -> int:  # rough fallback: ~4 chars/token
        return max(1, len(text) // 4)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    # required metadata (CLAUDE.md §5.5)
    chapter_number: int
    chapter_title: str
    knowledge_area: str
    section_path: str
    page_start: int
    page_end: int
    content_type: str
    process_group: str
    knowledge_base: str = config.KNOWLEDGE_BASE_NAME
    summary_method: str = ""  # set only on chapter_summary chunks (llm|extractive)

    def metadata(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("text")
        d.pop("chunk_id")
        return d


# --- chapter / process-group detection -------------------------------------
_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14,
}

# Endnotes/Index boundaries are detected by heading text, not page numbers, so
# this is robust to OCR page drift.
_ENDNOTE_RE = re.compile(r"\bend\s*notes?\b", re.I)
_INDEX_RE = re.compile(r"^\s*index\s*$", re.I)

_PROCESS_GROUP_KEYWORDS = [
    ("Initiating", ["develop project charter", "identify stakeholders",
                    "initiating"]),
    ("Closing", ["close project", "close phase", "closing"]),
    ("Monitoring & Controlling", ["monitor", "control", "validate scope",
                                  "perform integrated change"]),
    ("Executing", ["manage", "acquire", "develop team", "conduct procure",
                   "implement", "direct and manage", "executing"]),
    ("Planning", ["plan ", "develop schedule", "estimate", "create wbs",
                  "define ", "sequence activities", "planning"]),
]


def _match_chapter(text: str, chapter_map: dict | None = None) -> int | None:
    """Map a heading to a chapter number via known titles or 'Chapter N'."""
    chapter_map = chapter_map or config.CHAPTER_MAP
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    # explicit "chapter 5" / "chapter five"
    m = re.search(r"\bchapter\s+(\d{1,2})\b", t)
    if m:
        n = int(m.group(1))
        if n in chapter_map:
            return n
    m = re.search(r"\bchapter\s+([a-z]+)\b", t)
    if m and m.group(1) in _WORD_NUM:
        return _WORD_NUM[m.group(1)]
    # title match (allow the heading to be exactly/contain the known title)
    for num, meta in chapter_map.items():
        title = meta["title"].lower()
        if t == title or title in t:
            return num
        # match on the distinctive knowledge-area word (Scope, Cost, Risk...)
        ka = meta.get("knowledge_area", "").lower()
        if ka and ka not in ("cross_cutting", "exam_meta", "front_matter"):
            if re.search(rf"\b{re.escape(ka)}s?\b", t):
                return num
        first_word = title.split()[0]
        if len(first_word) >= 4 and re.fullmatch(rf"{first_word}s?", t):
            return num
    return None


def _detect_process_group(section_path: str) -> str:
    s = section_path.lower()
    for group, kws in _PROCESS_GROUP_KEYWORDS:
        if any(kw in s for kw in kws):
            return group
    return ""


def _looks_itto(text: str, nearby: str) -> bool:
    blob = (text + " " + nearby).lower()
    hits = sum(k in blob for k in ("input", "tool", "technique", "output"))
    return hits >= 2


def _looks_definition(text: str) -> bool:
    if count_tokens(text) > 60:
        return False
    # "Term: explanation" or "Term — explanation" leading pattern
    return bool(re.match(r"^[A-Z][A-Za-z0-9 /()\-]{2,40}\s*[:—\-]\s+\S", text))


# --- section grouping ------------------------------------------------------
@dataclass
class _Section:
    chapter_number: int
    chapter_title: str
    knowledge_area: str
    section_path: str
    page_start: int
    page_end: int
    is_endnotes: bool
    default_content_type: str
    elements: list[StructuredElement] = field(default_factory=list)


def _group_into_sections(elements: list[StructuredElement],
                         chapter_map: dict | None = None) -> list[_Section]:
    """Walk elements, maintaining chapter + heading stack, emit leaf sections."""
    chapter_map = chapter_map or config.CHAPTER_MAP
    sections: list[_Section] = []
    cur_chapter = 0
    cur_chapter_title = "Front Matter"
    cur_ka = "front_matter"
    cur_default_ct = "concept"
    heading_stack: list[tuple[int, str]] = []  # (level, text)
    in_endnotes = False
    skip_index = False
    current: _Section | None = None

    def section_path() -> str:
        ch = f"Ch.{cur_chapter} {cur_chapter_title}" if cur_chapter else \
            cur_chapter_title
        tail = " > ".join(t for _, t in heading_stack)
        return f"{ch} > {tail}" if tail else ch

    def flush():
        nonlocal current
        if current and current.elements:
            sections.append(current)
        current = None

    def start_section():
        nonlocal current
        flush()
        current = _Section(
            chapter_number=cur_chapter, chapter_title=cur_chapter_title,
            knowledge_area=cur_ka, section_path=section_path(),
            page_start=10**9, page_end=-1, is_endnotes=in_endnotes,
            default_content_type=cur_default_ct)

    for el in elements:
        # Exclude Index entirely; stop emitting once we hit it.
        if el.heading_level and _INDEX_RE.match(el.text):
            skip_index = True
            flush()
            continue
        if skip_index:
            continue

        if el.heading_level:
            # endnotes boundary
            if _ENDNOTE_RE.search(el.text):
                in_endnotes = True
            new_chapter = _match_chapter(el.text, chapter_map)
            if new_chapter is not None and el.heading_level <= 2:
                cur_chapter = new_chapter
                meta = chapter_map[new_chapter]
                cur_chapter_title = meta["title"]
                cur_ka = meta["knowledge_area"]
                cur_default_ct = meta["default_content_type"]
                heading_stack = [(el.heading_level, el.text)]
                in_endnotes = False
            else:
                # pop stack to this level, then push
                heading_stack = [(lvl, t) for lvl, t in heading_stack
                                 if lvl < el.heading_level]
                heading_stack.append((el.heading_level, el.text))
            start_section()
            continue

        if current is None:
            start_section()
        current.elements.append(el)
        current.page_start = min(current.page_start, el.page)
        current.page_end = max(current.page_end, el.page)

    flush()
    # fix empty page bounds
    for s in sections:
        if s.page_end < 0:
            s.page_start = s.page_end = 0
    return sections


# --- chunk emission --------------------------------------------------------
def _recursive_split(text: str, max_tokens: int, overlap: int) -> list[str]:
    """Split overlong narrative text on paragraph/sentence boundaries."""
    if count_tokens(text) <= max_tokens:
        return [text]
    paras = re.split(r"\n{2,}", text)
    pieces: list[str] = []
    buf = ""
    for p in paras:
        cand = (buf + "\n\n" + p).strip() if buf else p
        if count_tokens(cand) <= max_tokens:
            buf = cand
        else:
            if buf:
                pieces.append(buf)
            if count_tokens(p) <= max_tokens:
                buf = p
            else:  # a single giant paragraph: split by sentences
                sents = re.split(r"(?<=[.!?])\s+", p)
                sb = ""
                for s in sents:
                    c = (sb + " " + s).strip() if sb else s
                    if count_tokens(c) <= max_tokens:
                        sb = c
                    else:
                        if sb:
                            pieces.append(sb)
                        sb = s
                buf = sb
    if buf:
        pieces.append(buf)

    # add ~overlap tokens of tail from previous piece to the next
    if overlap > 0 and len(pieces) > 1:
        out = [pieces[0]]
        for i in range(1, len(pieces)):
            prev_words = pieces[i - 1].split()
            tail = " ".join(prev_words[-overlap:]) if prev_words else ""
            out.append((tail + " " + pieces[i]).strip())
        pieces = out
    return pieces


class HierarchicalChunker:
    def __init__(self, chapter_map: dict | None = None,
                 knowledge_base: str | None = None) -> None:
        self.target = config.CHUNK_TARGET_TOKENS
        self.max = config.CHUNK_MAX_TOKENS
        self.min = config.CHUNK_MIN_TOKENS
        self.chapter_map = chapter_map or config.CHAPTER_MAP
        self.knowledge_base = knowledge_base or config.KNOWLEDGE_BASE_NAME
        # prefix chunk ids per book so the shared Chroma collection never collides
        self._id_prefix = f"{config.kb_abbrev(self.knowledge_base).lower()}_"

    def chunk(self, elements: list[StructuredElement]
              ) -> tuple[list[Chunk], dict[str, str]]:
        sections = _group_into_sections(elements, self.chapter_map)
        chunks: list[Chunk] = []
        parent_store: dict[str, str] = {}
        seq = 0

        for sec in sections:
            if sec.knowledge_area == "exam_meta" and sec.chapter_number == 0:
                continue
            parent_text = "\n\n".join(e.text for e in sec.elements).strip()
            if not parent_text:
                continue
            parent_store[sec.section_path] = parent_text
            pgroup = _detect_process_group(sec.section_path)

            # separate atomic blocks (tables/formulas) from narrative
            narrative_parts: list[StructuredElement] = []
            atomic: list[tuple[StructuredElement, str]] = []
            for el in sec.elements:
                if el.block_type in _TABLE_TYPES:
                    nearby = sec.section_path
                    ct = "itto" if _looks_itto(el.text, nearby) else "concept"
                    atomic.append((el, ct))
                elif el.block_type in _FORMULA_TYPES:
                    atomic.append((el, "formula"))
                else:
                    narrative_parts.append(el)

            def emit(text: str, content_type: str, ps: int, pe: int):
                nonlocal seq
                text = text.strip()
                if not text:
                    return
                seq += 1
                chunks.append(Chunk(
                    chunk_id=f"{self._id_prefix}c{seq:05d}",
                    text=text,
                    chapter_number=sec.chapter_number,
                    chapter_title=sec.chapter_title,
                    knowledge_area=sec.knowledge_area,
                    section_path=sec.section_path,
                    page_start=ps, page_end=pe,
                    content_type=("endnote" if sec.is_endnotes else content_type),
                    process_group=pgroup,
                    knowledge_base=self.knowledge_base,
                ))

            # 1) atomic blocks, each its own chunk (formula: glue a bit of
            #    surrounding narrative for the worked example/explanation)
            narrative_text = "\n\n".join(e.text for e in narrative_parts).strip()
            for el, ct in atomic:
                body = el.text
                if ct == "formula" and narrative_text:
                    body = (narrative_text[:600] + "\n\n" + el.text).strip()
                emit(body, ct, el.page, el.page)

            # 2) narrative
            if not narrative_text:
                continue
            default_ct = sec.default_content_type
            if _looks_definition(narrative_text):
                default_ct = "definition"
            ntok = count_tokens(narrative_text)
            if ntok < self.min and chunks and not atomic:
                # merge tiny leaf into previous chunk of same chapter
                prev = chunks[-1]
                if prev.chapter_number == sec.chapter_number:
                    prev.text = (prev.text + "\n\n" + narrative_text).strip()
                    prev.page_end = max(prev.page_end, sec.page_end)
                    continue
            if ntok <= self.max:
                emit(narrative_text, default_ct, sec.page_start, sec.page_end)
            else:
                overlap = int(self.target * config.CHUNK_OVERLAP_RATIO)
                for piece in _recursive_split(narrative_text, self.max, overlap):
                    emit(piece, default_ct, sec.page_start, sec.page_end)

        logger.info("Chunked into %d chunks across %d parent sections.",
                    len(chunks), len(parent_store))
        return chunks, parent_store
