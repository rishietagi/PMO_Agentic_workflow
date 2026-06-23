"""Thin Groq client wrapper. Only the router should import this."""
from __future__ import annotations

import logging

from pmo_engine import config

logger = logging.getLogger(__name__)


class GroqRateLimitError(Exception):
    pass


class GroqClient:
    def __init__(self) -> None:
        if not config.groq_key_present():
            raise RuntimeError("GROQ_API_KEY missing/placeholder in .env")
        from groq import Groq
        self._client = Groq(api_key=config.GROQ_API_KEY)

    def chat(self, system: str, user: str, model: str,
             temperature: float = 0.2, max_tokens: int = 2048,
             json_mode: bool = False) -> str:
        from groq import APIStatusError, RateLimitError
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            raise GroqRateLimitError(str(exc)) from exc
        except APIStatusError as exc:
            if getattr(exc, "status_code", None) == 429:
                raise GroqRateLimitError(str(exc)) from exc
            raise
        return resp.choices[0].message.content or ""
