"""Unit tests that run without API keys or the built vector store.

Covers chunking logic, RRF fusion, BM25 metadata matching, router JSON
parsing, pydantic contracts, and the feedback store.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pmo_engine import config
from pmo_engine.chunking.hierarchical_chunker import (HierarchicalChunker,
                                                      _match_chapter,
                                                      count_tokens)
from pmo_engine.ocr.extract_structure import StructuredElement


# --- config / chapter map --------------------------------------------------
def test_chapter_map_has_all_14_chapters():
    assert set(config.CHAPTER_MAP) == set(range(1, 15))
    for meta in config.CHAPTER_MAP.values():
        assert "title" in meta and "knowledge_area" in meta


@pytest.mark.parametrize("text,expected", [
    ("Chapter 5", 5),
    ("CHAPTER FIVE", 5),
    ("Scope", 5),
    ("Risk", 11),
    ("Stakeholders", 13),
    ("Integration", 4),
    ("Some random heading", None),
])
def test_match_chapter(text, expected):
    assert _match_chapter(text) == expected


# --- chunker ---------------------------------------------------------------
def _elements():
    return [
        StructuredElement(0, 150, "SectionHeader", 1, "Chapter 5", ""),
        StructuredElement(1, 150, "SectionHeader", 3, "Create WBS", ""),
        StructuredElement(2, 150, "Text", None,
                          "The work breakdown structure decomposes scope. " * 20),
        StructuredElement(3, 151, "Table", None,
                          "Inputs | Tools and Techniques | Outputs\n"
                          "scope statement | decomposition | WBS", ""),
        StructuredElement(4, 152, "SectionHeader", 3, "Control Scope", ""),
        StructuredElement(5, 152, "Text", None, "Control scope monitors status."),
    ]


def test_chunker_produces_chunks_and_metadata():
    chunks, parents = HierarchicalChunker().chunk(_elements())
    assert chunks
    for c in chunks:
        assert c.chapter_number == 5
        assert c.knowledge_area == "Scope"
        assert c.section_path
        assert c.page_start <= c.page_end
        assert c.content_type in config.CONTENT_TYPES
    # the ITTO table is its own atomic chunk tagged itto
    assert any(c.content_type == "itto" for c in chunks)
    # parent store keyed by section_path
    assert parents


def test_chunker_respects_max_tokens_for_narrative():
    big = "This is a sentence about scope management requirements. " * 300
    els = [
        StructuredElement(0, 10, "SectionHeader", 1, "Chapter 5", ""),
        StructuredElement(1, 10, "SectionHeader", 2, "Big Section", ""),
        StructuredElement(2, 10, "Text", None, big),
    ]
    chunks, _ = HierarchicalChunker().chunk(els)
    narrative = [c for c in chunks if c.content_type == "concept"]
    assert len(narrative) > 1  # was split
    for c in narrative:
        # allow a little slack for overlap prefix
        assert count_tokens(c.text) <= config.CHUNK_MAX_TOKENS * 1.3


def test_chunker_excludes_index():
    els = [
        StructuredElement(0, 10, "SectionHeader", 1, "Chapter 5", ""),
        StructuredElement(1, 10, "Text", None, "Scope content here is useful."),
        StructuredElement(2, 523, "SectionHeader", 1, "Index", ""),
        StructuredElement(3, 523, "Text", None, "WBS, 150; Risk, 300"),
    ]
    chunks, _ = HierarchicalChunker().chunk(els)
    assert all("Index" not in c.section_path for c in chunks)


# --- retrieval fusion / matching ------------------------------------------
def test_rrf_fuse_prefers_items_high_in_both():
    from pmo_engine.retrieval.hybrid_retriever import _rrf_fuse
    dense = [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}]
    sparse = [{"chunk_id": "b"}, {"chunk_id": "a"}, {"chunk_id": "d"}]
    fused = _rrf_fuse(dense, sparse, k=60)
    ids = [f["chunk_id"] for f in fused]
    assert ids[0] in ("a", "b")  # appears high in both lists
    assert set(ids) == {"a", "b", "c", "d"}


def test_bm25_meta_match():
    from pmo_engine.retrieval.bm25_index import _meta_match
    m = {"knowledge_area": "Risk", "content_type": "itto"}
    assert _meta_match(m, {"knowledge_area": "Risk"})
    assert not _meta_match(m, {"knowledge_area": "Scope"})
    assert _meta_match(m, {"content_type": {"$in": ["itto", "formula"]}})
    assert _meta_match(m, {"$and": [{"knowledge_area": "Risk"},
                                    {"content_type": "itto"}]})


# --- router JSON parsing ---------------------------------------------------
@pytest.mark.parametrize("raw", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    'Sure! Here it is:\n{"a": 1}\nHope that helps.',
])
def test_extract_json(raw):
    from pmo_engine.llm.router import _extract_json
    assert _extract_json(raw) == {"a": 1}


# --- pydantic contracts ----------------------------------------------------
def test_citation_display_and_report_filters():
    from pmo_engine.agents.state import (Citation, ValidationFinding,
                                         ValidationReport)
    c = Citation(chapter_number=5, chapter_title="Scope", page_start=150,
                 page_end=152)
    assert "Ch.5" in c.display() and "pp.150-152" in c.display()
    rep = ValidationReport(findings=[
        ValidationFinding(knowledge_area="Scope", finding_type="gap",
                          statement="missing WBS"),
        ValidationFinding(knowledge_area="Risk", finding_type="risk_flag",
                          statement="no register"),
        ValidationFinding(knowledge_area="Cost", finding_type="alignment",
                          statement="ok"),
    ])
    assert len(rep.gaps()) == 1 and len(rep.risk_flags()) == 1


# --- feedback store --------------------------------------------------------
def test_feedback_store_aggregate(tmp_path):
    from pmo_engine.feedback.feedback_store import FeedbackStore
    fs = FeedbackStore(tmp_path / "fb.db")
    fs.record_feedback("run1", "Proj", 72, 4, True, "good")
    fs.record_gap_events("run1", [
        {"knowledge_area": "Risk", "category": "gap", "severity": "high",
         "title": "no register"},
        {"knowledge_area": "Risk", "category": "risk", "severity": "medium",
         "title": "vendor"},
    ])
    agg = fs.aggregate()
    assert agg["n_feedback"] == 1
    assert agg["avg_rating"] == 4.0
    assert agg["n_runs"] == 1
    assert ("Risk", 2) in agg["most_common_gap_areas"]
