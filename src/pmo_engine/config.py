"""Central config: paths, model names, chunk sizes, and the RITA chapter map.

Everything tunable lives here so the rest of the codebase imports constants
instead of hardcoding magic values. Env vars (loaded from .env) can override
the LLM model IDs without touching code.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --- Paths -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHROMA_DIR = DATA_DIR / "chroma_db"
PARENT_STORE_PATH = DATA_DIR / "parent_store.json"
BM25_INDEX_PATH = DATA_DIR / "bm25_index.pkl"
FEEDBACK_DB_PATH = DATA_DIR / "feedback.db"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Default source PDF. NOTE: actual file ships with spaces in the name; the
# CLAUDE.md reference uses underscores. We default to the real on-disk name.
DEFAULT_PDF_PATH = RAW_DIR / "RITA 10th Edition.pdf"
PMBOK_PDF_PATH = RAW_DIR / "PMBOK_Guide_6th.pdf"

CHROMA_COLLECTION = "pmo_knowledge_base"  # holds all books; filter via metadata
KNOWLEDGE_BASE_NAME = "RITA_10th_Edition"  # first member of an extensible KB


# --- Compute device (GPU when available) -----------------------------------
def resolve_device(preferred: str | None = None) -> str:
    """Return 'cuda' if a CUDA torch build + GPU are available, else 'cpu'.

    Override with env PMO_DEVICE=cpu|cuda. Torch is imported lazily so config
    stays cheap to import.
    """
    pref = (preferred or os.getenv("PMO_DEVICE", "auto")).lower()
    if pref == "cpu":
        return "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:  # noqa: BLE001
        pass
    return "cpu"


# Small-VRAM-safe surya/marker batch sizes (RTX 3050 = 4 GB). Applied as env
# vars by the OCR layer when running on CUDA so OCR doesn't OOM.
SURYA_GPU_BATCH = {
    "RECOGNITION_BATCH_SIZE": os.getenv("RECOGNITION_BATCH_SIZE", "16"),
    "DETECTOR_BATCH_SIZE": os.getenv("DETECTOR_BATCH_SIZE", "6"),
    "LAYOUT_BATCH_SIZE": os.getenv("LAYOUT_BATCH_SIZE", "6"),
    "TABLE_REC_BATCH_SIZE": os.getenv("TABLE_REC_BATCH_SIZE", "6"),
    "OCR_ERROR_BATCH_SIZE": os.getenv("OCR_ERROR_BATCH_SIZE", "6"),
}

# --- Env / secrets ---------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

_PLACEHOLDERS = {"", "your_groq_api_key_here", "your_google_api_key_here"}


def groq_key_present() -> bool:
    return GROQ_API_KEY not in _PLACEHOLDERS


def google_key_present() -> bool:
    return GOOGLE_API_KEY not in _PLACEHOLDERS


# --- LLM model IDs (verified 2026-06-21; override via .env) -----------------
# Routing: small model for cheap/high-volume steps, large for reasoning.
GROQ_MODEL_LARGE = os.getenv("GROQ_MODEL_LARGE", "llama-3.3-70b-versatile")
GROQ_MODEL_SMALL = os.getenv("GROQ_MODEL_SMALL", "llama-3.1-8b-instant")
# gemini-2.5-flash is the documented safe free-tier default. Newer
# gemini-3.5-flash / gemini-3.1-flash-lite exist (see NOTES.md) — override
# via GEMINI_MODEL if confirmed available on your key.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# --- Local models (upgraded for GPU; fp16 keeps them inside 4 GB VRAM) ------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
# tried in order if the primary reranker fails to load (e.g. VRAM):
RERANKER_FALLBACKS = ["BAAI/bge-reranker-base",
                      "cross-encoder/ms-marco-MiniLM-L-6-v2"]


def use_fp16() -> bool:
    """Half precision on CUDA (halves VRAM, ~same quality). Off on CPU."""
    return resolve_device() == "cuda" and os.getenv("PMO_FP16", "1") != "0"

# --- Chunking knobs --------------------------------------------------------
CHUNK_TARGET_TOKENS = 450      # midpoint of the 300-600 target band
CHUNK_MAX_TOKENS = 600
CHUNK_MIN_TOKENS = 80          # below this, merge up into parent intro
CHUNK_OVERLAP_RATIO = 0.15

# --- Retrieval knobs -------------------------------------------------------
HYBRID_TOP_K = 20             # fused shortlist size before rerank
RERANK_TOP_K = 5             # final chunks into the LLM context
RRF_K = 60                    # reciprocal rank fusion constant

# --- Knowledge-area / chapter map (CLAUDE.md §1, verified by inspection) ----
# chapter_number -> metadata. knowledge_area is the retrieval pre-filter key.
CHAPTER_MAP: dict[int, dict[str, str]] = {
    1: {"title": "Tricks of the Trade for Studying for This Exam",
        "knowledge_area": "exam_meta", "default_content_type": "exam_tip"},
    2: {"title": "Framework",
        "knowledge_area": "cross_cutting", "default_content_type": "concept"},
    3: {"title": "Processes and Domains",
        "knowledge_area": "cross_cutting", "default_content_type": "concept"},
    4: {"title": "Integration",
        "knowledge_area": "Integration", "default_content_type": "concept"},
    5: {"title": "Scope",
        "knowledge_area": "Scope", "default_content_type": "concept"},
    6: {"title": "Schedule",
        "knowledge_area": "Schedule", "default_content_type": "concept"},
    7: {"title": "Cost",
        "knowledge_area": "Cost", "default_content_type": "concept"},
    8: {"title": "Quality",
        "knowledge_area": "Quality", "default_content_type": "concept"},
    9: {"title": "Resources",
        "knowledge_area": "Resources", "default_content_type": "concept"},
    10: {"title": "Communications",
         "knowledge_area": "Communications", "default_content_type": "concept"},
    11: {"title": "Risk",
         "knowledge_area": "Risk", "default_content_type": "concept"},
    12: {"title": "Procurement",
         "knowledge_area": "Procurement", "default_content_type": "concept"},
    13: {"title": "Stakeholders",
         "knowledge_area": "Stakeholders", "default_content_type": "concept"},
    14: {"title": "Tips for Passing the PMP Exam the First Time",
         "knowledge_area": "exam_meta", "default_content_type": "common_pitfall"},
}

# The knowledge areas that map ~1:1 to generated plan sections (Ch.5-13).
PLAN_KNOWLEDGE_AREAS = [
    "Integration", "Scope", "Schedule", "Cost", "Quality", "Resources",
    "Communications", "Risk", "Procurement", "Stakeholders",
]

CONTENT_TYPES = [
    "itto", "formula", "definition", "exam_tip", "common_pitfall",
    "concept", "chapter_summary", "endnote",
]

# --- PMBOK Guide 6th Edition chapter map -----------------------------------
# PMBOK 6th Part 1 chapters 4-13 are the ten knowledge areas (same areas as
# RITA), so retrieval's knowledge_area pre-filter spans both books uniformly.
PMBOK_CHAPTER_MAP: dict[int, dict[str, str]] = {
    1: {"title": "Introduction",
        "knowledge_area": "cross_cutting", "default_content_type": "concept"},
    2: {"title": "The Environment in Which Projects Operate",
        "knowledge_area": "cross_cutting", "default_content_type": "concept"},
    3: {"title": "The Role of the Project Manager",
        "knowledge_area": "cross_cutting", "default_content_type": "concept"},
    4: {"title": "Project Integration Management",
        "knowledge_area": "Integration", "default_content_type": "concept"},
    5: {"title": "Project Scope Management",
        "knowledge_area": "Scope", "default_content_type": "concept"},
    6: {"title": "Project Schedule Management",
        "knowledge_area": "Schedule", "default_content_type": "concept"},
    7: {"title": "Project Cost Management",
        "knowledge_area": "Cost", "default_content_type": "concept"},
    8: {"title": "Project Quality Management",
        "knowledge_area": "Quality", "default_content_type": "concept"},
    9: {"title": "Project Resource Management",
        "knowledge_area": "Resources", "default_content_type": "concept"},
    10: {"title": "Project Communications Management",
         "knowledge_area": "Communications", "default_content_type": "concept"},
    11: {"title": "Project Risk Management",
         "knowledge_area": "Risk", "default_content_type": "concept"},
    12: {"title": "Project Procurement Management",
         "knowledge_area": "Procurement", "default_content_type": "concept"},
    13: {"title": "Project Stakeholder Management",
         "knowledge_area": "Stakeholders", "default_content_type": "concept"},
}

# --- Knowledge-base registry (extensible; RITA + PMBOK for v1) --------------
KNOWLEDGE_BASES: dict[str, dict] = {
    "RITA_10th_Edition": {
        "display": "RITA PMP Prep (10th Ed.)", "abbrev": "RITA",
        "chapter_map": CHAPTER_MAP, "pdf": DEFAULT_PDF_PATH,
        "needs_ocr": True,
    },
    "PMBOK_Guide_6th": {
        "display": "PMBOK Guide (6th Ed.)", "abbrev": "PMBOK",
        "chapter_map": PMBOK_CHAPTER_MAP, "pdf": PMBOK_PDF_PATH,
        "needs_ocr": False,   # digital PDF with a text layer
    },
}


def kb_abbrev(kb_name: str) -> str:
    return KNOWLEDGE_BASES.get(kb_name, {}).get("abbrev", kb_name or "REF")
