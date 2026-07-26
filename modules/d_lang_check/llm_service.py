"""
llm_service.py — Unified LLM client for DeepSeek API.

All D module capabilities use this single module for LLM calls.
Configure via DEEPSEEK_API_KEY environment variable.

Usage:
    from modules.d_lang_check.llm_service import call_llm, parse_json_response
    raw = call_llm(system_prompt, user_message, json_mode=True)
    data = parse_json_response(raw)
"""

from __future__ import annotations

import json
import os
import re
import logging
import time

logger = logging.getLogger("autoresearch.d_lang_check.llm")

# Configuration
_API_BASE = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = os.environ.get("BACKUP_LLM_MODEL", "deepseek-v4-pro")
_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


class LLMServiceError(Exception):
    """LLM service error."""
    def __init__(self, message: str, code: str = "LLM_ERROR", status: int = 500):
        super().__init__(message)
        self.code = code
        self.status = status


def call_llm(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    json_mode: bool = False,
    max_retries: int = 3,
    timeout: int = 120,
) -> str:
    """Call DeepSeek LLM API with retry and JSON fault-tolerance.

    Args:
        system_prompt: System-level instruction (persona + constraints)
        user_message:  User prompt with input text
        model:         Model override (default: deepseek-v4-pro)
        temperature:   Sampling temperature (0.0-1.0)
        max_tokens:    Max output tokens
        json_mode:     If True, enable JSON response format
        max_retries:   Retry count with exponential backoff
        timeout:       Request timeout in seconds

    Returns:
        Raw LLM response text

    Raises:
        LLMServiceError: On missing API key or API failure after all retries
    """
    if not _API_KEY:
        raise LLMServiceError(
            "DEEPSEEK_API_KEY environment variable not set. "
            "Set it to your DeepSeek API key.",
            code="NO_API_KEY", status=401,
        )

    model = model or _DEFAULT_MODEL
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for attempt in range(max_retries):
        try:
            return _call_deepseek(messages, model, temperature, max_tokens, json_mode, timeout)
        except Exception as e:
            logger.warning("LLM call attempt %d/%d failed: %s", attempt + 1, max_retries, e)
            if attempt == max_retries - 1:
                raise LLMServiceError(
                    f"DeepSeek API call failed after {max_retries} retries: {e}",
                    code="API_ERROR", status=502,
                )
            time.sleep(2 ** attempt)


def parse_json_response(raw: str) -> dict | list:
    """Fault-tolerant JSON parsing for LLM responses.

    Handles: markdown code fences, trailing commas, truncated JSON,
    and JSON wrapped in explanatory text.
    """
    raw = raw.strip()

    # Strip markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fix trailing commas
    fixed = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON array or object from mixed text
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        idx_s = raw.find(start_char)
        idx_e = raw.rfind(end_char)
        if idx_s >= 0 and idx_e > idx_s:
            try:
                return json.loads(raw[idx_s:idx_e + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Failed to parse LLM JSON response: {raw[:200]}...")


def _call_deepseek(
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    timeout: int,
) -> str:
    """Call DeepSeek Chat Completions API (OpenAI-compatible)."""
    import httpx

    headers = {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    response = httpx.post(
        f"{_API_BASE}/chat/completions",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]
