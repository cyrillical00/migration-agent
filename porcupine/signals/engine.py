"""
LLM signal engine.

Orchestrates parallel LiteLLM calls to Claude Sonnet, Gemini Flash, and local
Ollama. Handles structured JSON extraction with one retry on parse failure.
Returns a list of ModelSignal objects that the CLI renders and Supabase stores.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import litellm
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from signals.prompts import SYSTEM_PROMPT, build_user_prompt, build_retry_prompt
from ingestion.polymarket import Market

load_dotenv()

# ---------------------------------------------------------------------------
# Model roster
# ---------------------------------------------------------------------------

MODELS = [
    {
        "name": "claude",
        "label": "Claude Sonnet",
        "model_id": "claude-sonnet-4-20250514",
        "kwargs": {},
    },
    {
        "name": "gemini",
        "label": "Gemini Flash",
        "model_id": "gemini/gemini-2.0-flash",
        "kwargs": {},
    },
    {
        "name": "ollama",
        "label": "Ollama (qwen2.5-coder:32b)",
        "model_id": "ollama/qwen2.5-coder:32b",
        "kwargs": {
            "api_base": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        },
    },
]

# Silence LiteLLM's verbose logging by default
litellm.suppress_debug_info = True
litellm.set_verbose = False


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ModelSignal:
    model_name: str          # e.g. "claude"
    model_label: str         # display label
    estimate: Optional[float]
    rationale: Optional[str]
    confidence: Optional[str]  # "low" | "medium" | "high"
    latency_ms: int
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.estimate is not None and self.error is None

    def to_dict(self) -> dict:
        return {
            "model": self.model_name,
            "label": self.model_label,
            "estimate": self.estimate,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


@dataclass
class EnsembleResult:
    market_id: str
    signals: list[ModelSignal] = field(default_factory=list)

    @property
    def mean_estimate(self) -> Optional[float]:
        estimates = [s.estimate for s in self.signals if s.ok]
        if not estimates:
            return None
        return sum(estimates) / len(estimates)

    def to_json_list(self) -> list[dict]:
        return [s.to_dict() for s in self.signals]


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

_JSON_RE = re.compile(
    r'\{[^{}]*"estimate"\s*:\s*[\d.]+[^{}]*\}',
    re.DOTALL,
)


def _extract_json(text: str) -> dict:
    """
    Extract the signal JSON from a potentially noisy LLM response.

    Tries in order:
    1. Direct json.loads on the full response (model was well-behaved)
    2. Regex to find the JSON object containing "estimate"
    3. Raises ValueError if neither works
    """
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block after a markdown fence
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Try regex extraction
    match = _JSON_RE.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from response: {text[:200]!r}")


def _validate_signal(data: dict) -> tuple[float, str, str]:
    """Validate and normalize the extracted JSON fields."""
    estimate = float(data.get("estimate", -1))
    if not (0.0 <= estimate <= 1.0):
        raise ValueError(f"estimate out of range: {estimate}")
    rationale = str(data.get("rationale", "")).strip() or "No rationale provided."
    confidence = str(data.get("confidence", "")).lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "medium"
    return estimate, rationale, confidence


# ---------------------------------------------------------------------------
# Per-model call with retry
# ---------------------------------------------------------------------------

def _call_model(model_cfg: dict, messages: list[dict]) -> tuple[str, int]:
    """
    Call a single LiteLLM model and return (response_text, latency_ms).
    Raises on API error.
    """
    start = time.monotonic()
    response = litellm.completion(
        model=model_cfg["model_id"],
        messages=messages,
        temperature=0.2,
        max_tokens=1024,
        **model_cfg.get("kwargs", {}),
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    content = response.choices[0].message.content or ""
    return content, elapsed_ms


def _query_model(model_cfg: dict, market: Market) -> ModelSignal:
    """
    Query one model with CoT prompt, retry once on JSON parse failure.
    Never raises — errors are captured in ModelSignal.error.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(
                question=market.question,
                implied_prob=market.implied_prob or 0.5,
                end_date=market.end_date,
            ),
        },
    ]

    total_latency = 0

    # Attempt 1: full CoT prompt
    try:
        text, latency_ms = _call_model(model_cfg, messages)
        total_latency += latency_ms
    except Exception as exc:
        # Summarize the error to a single readable line
        err_str = str(exc)
        if "AuthenticationError" in type(exc).__name__ or "authentication" in err_str.lower():
            short_err = "API key missing or invalid"
        elif "ConnectionError" in type(exc).__name__ or "refused" in err_str.lower() or "connect" in err_str.lower():
            short_err = "Connection refused — is the service running?"
        elif "RateLimitError" in type(exc).__name__:
            short_err = "Rate limit hit"
        elif "Timeout" in type(exc).__name__:
            short_err = "Timed out"
        else:
            short_err = err_str[:80]
        return ModelSignal(
            model_name=model_cfg["name"],
            model_label=model_cfg["label"],
            estimate=None,
            rationale=None,
            confidence=None,
            latency_ms=0,
            error=short_err,
        )

    # Try to parse JSON from the response
    try:
        data = _extract_json(text)
        estimate, rationale, confidence = _validate_signal(data)
        return ModelSignal(
            model_name=model_cfg["name"],
            model_label=model_cfg["label"],
            estimate=estimate,
            rationale=rationale,
            confidence=confidence,
            latency_ms=total_latency,
        )
    except (ValueError, KeyError, TypeError):
        pass  # fall through to retry

    # Attempt 2: retry with stripped prompt demanding only JSON
    retry_messages = messages + [
        {"role": "assistant", "content": text},
        {"role": "user", "content": build_retry_prompt()},
    ]
    try:
        text2, latency2 = _call_model(model_cfg, retry_messages)
        total_latency += latency2
        data = _extract_json(text2)
        estimate, rationale, confidence = _validate_signal(data)
        return ModelSignal(
            model_name=model_cfg["name"],
            model_label=model_cfg["label"],
            estimate=estimate,
            rationale=rationale,
            confidence=confidence,
            latency_ms=total_latency,
        )
    except Exception as exc:
        return ModelSignal(
            model_name=model_cfg["name"],
            model_label=model_cfg["label"],
            estimate=None,
            rationale=None,
            confidence=None,
            latency_ms=total_latency,
            error=f"JSON parse failed after retry: {exc}",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ensemble(market: Market, models: list[dict] | None = None) -> EnsembleResult:
    """
    Query all LLM models in sequence and return an EnsembleResult.

    Models are called sequentially to stay within rate limits and because the
    30-second SLA is per-market (not per-model). Parallel calls would risk
    hitting provider rate limits simultaneously.

    Args:
        market: Normalized Market object from the ingestion layer.
        models: Override the default MODELS list (useful for testing).

    Returns:
        EnsembleResult containing per-model signals and computed mean estimate.
    """
    active_models = models if models is not None else MODELS
    result = EnsembleResult(market_id=market.condition_id)

    for model_cfg in active_models:
        signal = _query_model(model_cfg, market)
        result.signals.append(signal)

    return result
