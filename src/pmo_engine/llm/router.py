"""LLM router (CLAUDE.md §3/§4/§9).

Single entry point for every LLM call in the system. Responsibilities:
  * Cheap-vs-expensive routing: CHEAP tier -> Groq llama-3.1-8b-instant for
    high-volume steps (intake extraction, sub-query gen, classification);
    REASONING tier -> Groq llama-3.3-70b-versatile for validation synthesis
    and recommendations.
  * Provider fallback: Groq primary -> Gemini fallback on rate-limit/error.
  * Exponential backoff with jitter (free-tier 429s are routine, §4).
No agent code may call the Groq/Gemini SDKs directly (§9).
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from enum import Enum
from typing import Any

from pmo_engine import config
from pmo_engine.llm.groq_client import GroqClient, GroqRateLimitError

logger = logging.getLogger(__name__)


class TaskTier(str, Enum):
    CHEAP = "cheap"          # 8B instant: extraction, sub-queries, classify
    REASONING = "reasoning"  # 70B: validation synthesis, recommendations


class LLMUnavailableError(RuntimeError):
    pass


class LLMRouter:
    def __init__(self, max_retries: int = 4, base_delay: float = 1.5) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._groq: GroqClient | None = None
        self._gemini = None
        self._groq_ok = config.groq_key_present()
        self._gemini_ok = config.google_key_present()

    # -- lazy clients -------------------------------------------------------
    @property
    def groq(self) -> GroqClient:
        if self._groq is None:
            self._groq = GroqClient()
        return self._groq

    @property
    def gemini(self):
        if self._gemini is None:
            from pmo_engine.llm.gemini_client import GeminiClient
            self._gemini = GeminiClient()
        return self._gemini

    def providers_available(self) -> bool:
        return self._groq_ok or self._gemini_ok

    @staticmethod
    def _model_for(tier: TaskTier) -> str:
        return (config.GROQ_MODEL_SMALL if tier == TaskTier.CHEAP
                else config.GROQ_MODEL_LARGE)

    # -- core call ----------------------------------------------------------
    def complete(self, system: str, user: str,
                 tier: TaskTier = TaskTier.REASONING,
                 temperature: float = 0.2, max_tokens: int = 2048,
                 json_mode: bool = False) -> str:
        if not self.providers_available():
            raise LLMUnavailableError(
                "No usable API keys. Set GROQ_API_KEY (and optionally "
                "GOOGLE_API_KEY) in .env.")

        # 1) Groq primary with exponential backoff on rate limits.
        if self._groq_ok:
            model = self._model_for(tier)
            for attempt in range(self.max_retries):
                try:
                    return self.groq.chat(system, user, model=model,
                                          temperature=temperature,
                                          max_tokens=max_tokens,
                                          json_mode=json_mode)
                except GroqRateLimitError as exc:
                    delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning("Groq 429 (attempt %d/%d), backing off %.1fs",
                                   attempt + 1, self.max_retries, delay)
                    if attempt == self.max_retries - 1:
                        logger.warning("Groq exhausted retries; falling back.")
                        break
                    time.sleep(delay)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Groq error (%s); falling back to Gemini.", exc)
                    break

        # 2) Gemini fallback.
        if self._gemini_ok:
            try:
                logger.info("Routing to Gemini fallback (%s).", config.GEMINI_MODEL)
                return self.gemini.chat(system, user, temperature=temperature,
                                        max_tokens=max_tokens, json_mode=json_mode)
            except Exception as exc:  # noqa: BLE001
                raise LLMUnavailableError(f"Both providers failed: {exc}") from exc

        raise LLMUnavailableError("Groq failed and no Gemini fallback configured.")

    def complete_json(self, system: str, user: str,
                      tier: TaskTier = TaskTier.REASONING,
                      temperature: float = 0.1,
                      max_tokens: int = 2048) -> dict[str, Any]:
        """Call expecting JSON; tolerant of fenced/loose JSON output."""
        raw = self.complete(system, user, tier=tier, temperature=temperature,
                            max_tokens=max_tokens, json_mode=True)
        return _extract_json(raw)


def _extract_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # strip code fences
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # first {...} or [...] balanced-ish span
    m = re.search(r"(\{.*\}|\[.*\])", raw, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    logger.error("Could not parse JSON from LLM output: %s", raw[:300])
    return {}


# module-level singleton for convenience
_default_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _default_router
    if _default_router is None:
        _default_router = LLMRouter()
    return _default_router
