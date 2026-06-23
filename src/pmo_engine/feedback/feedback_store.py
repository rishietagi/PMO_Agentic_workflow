"""Feedback capture (CLAUDE.md §7) — SQLite, instrumentation only.

This is where Steps 7-8 (Feedback Loop / Continuous Improvement) are
instrumented for the POC. It captures user ratings/comments on an
OptimizedPlan plus the gap types flagged in a run, and exposes a simple
aggregate view. It deliberately does NOT auto-retrain or auto-tune prompts —
that's a documented Phase 2 item, not a silent omission.
"""
from __future__ import annotations

import logging
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pmo_engine import config

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    project_title TEXT,
    compliance_score INTEGER,
    rating INTEGER,
    helpful INTEGER,
    comment TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS gap_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    knowledge_area TEXT,
    category TEXT,
    severity TEXT,
    title TEXT,
    created_at TEXT
);
"""


class FeedbackStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or config.FEEDBACK_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_feedback(self, run_id: str, project_title: str,
                        compliance_score: int, rating: int,
                        helpful: bool, comment: str = "") -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO feedback (run_id, project_title, compliance_score, "
                "rating, helpful, comment, created_at) VALUES (?,?,?,?,?,?,?)",
                (run_id, project_title, compliance_score, rating,
                 int(helpful), comment, self._now()))
        logger.info("Recorded feedback for run %s (rating=%s).", run_id, rating)

    def record_gap_events(self, run_id: str, items: list[dict[str, Any]]) -> None:
        rows = [(run_id, it.get("knowledge_area", ""), it.get("category", ""),
                 it.get("severity", ""), it.get("title", ""), self._now())
                for it in items]
        with self._conn() as c:
            c.executemany(
                "INSERT INTO gap_events (run_id, knowledge_area, category, "
                "severity, title, created_at) VALUES (?,?,?,?,?,?)", rows)

    # --- aggregate views (surfaced in the Streamlit app) ------------------
    def aggregate(self) -> dict[str, Any]:
        with self._conn() as c:
            fb = c.execute("SELECT * FROM feedback").fetchall()
            gaps = c.execute("SELECT * FROM gap_events").fetchall()
        ratings = [r["rating"] for r in fb if r["rating"] is not None]
        ka_counts = Counter(g["knowledge_area"] for g in gaps if g["knowledge_area"])
        cat_counts = Counter(g["category"] for g in gaps if g["category"])
        return {
            "n_feedback": len(fb),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "pct_helpful": (round(100 * sum(r["helpful"] for r in fb) / len(fb))
                            if fb else None),
            "most_common_gap_areas": ka_counts.most_common(8),
            "gap_vs_risk": dict(cat_counts),
            "n_runs": len({g["run_id"] for g in gaps}),
            "recent_comments": [r["comment"] for r in fb[-5:] if r["comment"]],
        }
