"""Local cross-encoder reranker (CLAUDE.md §3/§6.4).

Reranks the fused hybrid shortlist down to the few chunks that actually enter
the LLM context. Runs locally on CPU — no API budget spent.
"""
from __future__ import annotations

import logging
from typing import Any

from pmo_engine import config

logger = logging.getLogger(__name__)


class Reranker:
    _model = None
    _active = None

    @classmethod
    def _get(cls):
        if cls._model is None:
            from sentence_transformers import CrossEncoder
            device = config.resolve_device()
            candidates = [config.RERANKER_MODEL, *config.RERANKER_FALLBACKS]
            for name in candidates:
                try:
                    logger.info("Loading reranker %s on %s (fp16=%s) ...",
                                name, device, config.use_fp16())
                    model = CrossEncoder(name, device=device)
                    if config.use_fp16():
                        try:
                            model.model.half()
                        except Exception:  # noqa: BLE001
                            pass
                    cls._model = model
                    cls._active = name
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Reranker %s failed to load (%s); trying "
                                   "next.", name, exc)
            if cls._model is None:
                raise RuntimeError("No reranker could be loaded.")
        return cls._model

    @classmethod
    def rerank(cls, query: str, candidates: list[dict[str, Any]],
               top_k: int = config.RERANK_TOP_K) -> list[dict[str, Any]]:
        if not candidates:
            return []
        try:
            model = cls._get()
            pairs = [(query, c["text"]) for c in candidates]
            scores = model.predict(pairs)
            for c, s in zip(candidates, scores):
                c["rerank_score"] = float(s)
            ranked = sorted(candidates, key=lambda c: c["rerank_score"],
                            reverse=True)
        except Exception as exc:  # noqa: BLE001 - fall back to fused order
            logger.warning("Reranker unavailable (%s); using fused order.", exc)
            ranked = candidates
        return ranked[:top_k]
