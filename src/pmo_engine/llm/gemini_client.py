"""Thin Gemini client wrapper (current google-genai SDK). Router-only import.

Used as the fallback when Groq is rate-limited, and for second-opinion
validation scoring. Per CLAUDE.md §4: free tier is Flash/Flash-Lite only;
don't send anything beyond RITA content + synthetic SOWs through it.
"""
from __future__ import annotations

import logging

from pmo_engine import config

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self) -> None:
        if not config.google_key_present():
            raise RuntimeError("GOOGLE_API_KEY missing/placeholder in .env")
        from google import genai
        self._client = genai.Client(api_key=config.GOOGLE_API_KEY)

    def chat(self, system: str, user: str, model: str | None = None,
             temperature: float = 0.2, max_tokens: int = 2048,
             json_mode: bool = False) -> str:
        from google.genai import types
        model = model or config.GEMINI_MODEL
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if json_mode else "text/plain",
        )
        resp = self._client.models.generate_content(
            model=model, contents=user, config=cfg)
        return resp.text or ""
