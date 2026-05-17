"""
Anthropic API client for the AI Intelligence Tracking System.

Provides four operations:
  classify_batch      — batch-classify raw search results (haiku)
  score_bottleneck    — score one infrastructure bottleneck layer (sonnet)
  score_adoption      — score one industry's agent adoption (sonnet)
  synthesize_memo     — produce the weekly synthesis memo (sonnet)

All calls:
  - Use ephemeral cache_control on system prompts
  - Use forced tool_choice for structured JSON output
  - Retry on HTTP 429 (RateLimitError) with exponential back-off
  - Log timing, token counts, and cost to src.db.log_api_call
"""

import json
import logging
import os
import time
from typing import Optional

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import src.db as db
from config import (
    LAYER_RUBRICS,
    MODEL_CLASSIFY,
    MODEL_MEMO,
    MODEL_SCORE,
    PROMPTS_DIR,
)
from src.models import ClassifyResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing constants (per million tokens)
# ---------------------------------------------------------------------------

_PRICES: dict[str, dict[str, float]] = {
    # claude-haiku-4-5-20251001
    MODEL_CLASSIFY: {
        "input":         0.80,
        "output":        4.00,
        "cache_read":    0.08,   # 10% of input price
        "cache_write":   1.00,   # 1.25× input price
    },
    # claude-sonnet-4-6
    MODEL_SCORE: {
        "input":         3.00,
        "output":       15.00,
        "cache_read":    0.30,   # 10% of input price
        "cache_write":   3.75,   # 1.25× input price
    },
}
# MODEL_MEMO is the same model string as MODEL_SCORE
_PRICES[MODEL_MEMO] = _PRICES[MODEL_SCORE]


def _compute_cost(model: str, usage) -> float:
    """Calculate cost in USD from an Anthropic usage object."""
    prices = _PRICES.get(model, _PRICES[MODEL_SCORE])
    per_million = 1_000_000.0

    input_tok  = getattr(usage, "input_tokens", 0) or 0
    output_tok = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0

    cost = (
        input_tok   * prices["input"]       / per_million
        + output_tok  * prices["output"]      / per_million
        + cache_read  * prices["cache_read"]  / per_million
        + cache_write * prices["cache_write"] / per_million
    )
    return round(cost, 8)


# ---------------------------------------------------------------------------
# Shared low-level call helper
# ---------------------------------------------------------------------------

def _build_retry_decorator():
    """Build a tenacity retry decorator for RateLimitError only."""
    return retry(
        retry=retry_if_exception_type(anthropic.RateLimitError),
        wait=wait_exponential(multiplier=1, min=5, max=120),
        stop=stop_after_attempt(3),
        reraise=True,
    )


_anthropic_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY environment variable is not set")
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


def _call_tool(
    *,
    model: str,
    system_text: str,
    user_text: str,
    tool_name: str,
    tool_description: str,
    tool_schema: dict,
    operation: str,
    run_id: Optional[int],
    max_tokens: int = 4096,
) -> dict:
    """
    Make a single forced-tool-call request to the Anthropic API.

    Returns the parsed tool input dict. Raises on unexpected response shape.
    Logs every attempt (success or failure) to src.db.log_api_call.
    Retries on RateLimitError with exponential back-off (max 3 attempts).
    """
    client = _get_client()

    system_block = [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    tool_def = {
        "name": tool_name,
        "description": tool_description,
        "input_schema": tool_schema,
    }

    @_build_retry_decorator()
    def _attempt() -> dict:
        t0 = time.monotonic()
        error_msg: Optional[str] = None
        response = None

        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_block,
                messages=[{"role": "user", "content": user_text}],
                tools=[tool_def],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except anthropic.RateLimitError:
            duration_ms = int((time.monotonic() - t0) * 1000)
            db.log_api_call(
                run_id=run_id,
                provider="anthropic",
                operation=operation,
                duration_ms=duration_ms,
                succeeded=False,
                model=model,
                error="RateLimitError (429) — will retry",
            )
            raise  # tenacity will catch and retry
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_msg = str(exc)
            db.log_api_call(
                run_id=run_id,
                provider="anthropic",
                operation=operation,
                duration_ms=duration_ms,
                succeeded=False,
                model=model,
                error=error_msg,
            )
            raise

        duration_ms = int((time.monotonic() - t0) * 1000)
        usage = response.usage
        cost = _compute_cost(model, usage)

        db.log_api_call(
            run_id=run_id,
            provider="anthropic",
            operation=operation,
            duration_ms=duration_ms,
            succeeded=True,
            model=model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            cache_read=getattr(usage, "cache_read_input_tokens", None),
            cache_write=getattr(usage, "cache_creation_input_tokens", None),
            cost_usd=cost,
        )

        # Extract the tool_use block
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input  # already a dict

        raise ValueError(
            f"Claude response for operation '{operation}' did not contain a "
            f"'{tool_name}' tool_use block. "
            f"Stop reason: {response.stop_reason}. "
            f"Content types: {[b.type for b in response.content]}"
        )

    return _attempt()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_batch(
    items: list[dict],
    run_id: Optional[int] = None,
) -> list[ClassifyResult]:
    """
    Classify a batch of search result items for relevance to AI infrastructure
    bottleneck or agent adoption tracking.

    Args:
        items: list of {index, title, snippet, url}
        run_id: optional run ID for logging

    Returns:
        list of ClassifyResult dataclasses (same length as input, indexed by .index)
    """
    system_text = (PROMPTS_DIR / "classify_signal.txt").read_text(encoding="utf-8")

    # Numbered JSON list so Claude can correlate indices
    user_text = json.dumps(
        [{"index": it["index"], "title": it["title"],
          "snippet": it["snippet"], "url": it["url"]}
         for it in items],
        indent=2,
    )

    tool_schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index":       {"type": "integer"},
                        "is_relevant": {"type": "boolean"},
                        "relevance":   {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "importance":  {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "summary":     {"type": "string"},
                    },
                    "required": ["index", "is_relevant", "relevance", "importance", "summary"],
                },
            }
        },
        "required": ["results"],
    }

    result_dict = _call_tool(
        model=MODEL_CLASSIFY,
        system_text=system_text,
        user_text=user_text,
        tool_name="classify_results",
        tool_description=(
            "Return classification results for every item in the input batch."
        ),
        tool_schema=tool_schema,
        operation="classify_batch",
        run_id=run_id,
        max_tokens=4096,
    )

    classify_results: list[ClassifyResult] = []
    for r in result_dict.get("results", []):
        classify_results.append(
            ClassifyResult(
                index=int(r["index"]),
                is_relevant=bool(r["is_relevant"]),
                relevance=float(r.get("relevance", 0.0)),
                importance=float(r.get("importance", 0.0)),
                summary=str(r.get("summary", "")),
            )
        )
    return classify_results


def score_bottleneck(
    layer: str,
    iso_week: str,
    prior_score: Optional[int],
    signals: list[dict],
    run_id: Optional[int] = None,
) -> dict:
    """
    Score one AI infrastructure bottleneck layer on a 1–5 scale.

    Args:
        layer:       one of LAYERS (e.g. "gpu", "hbm")
        iso_week:    current ISO week string (e.g. "2026-W20")
        prior_score: last week's score for this layer, or None
        signals:     classified signal dicts from DB (each has url, summary, importance)
        run_id:      optional run ID for logging

    Returns:
        dict with keys: score, confidence, rationale, leading_indicators, evidence_urls
    """
    layer_rubric = LAYER_RUBRICS.get(layer, "No rubric available for this layer.")

    system_text = (
        (PROMPTS_DIR / "score_bottleneck.txt")
        .read_text(encoding="utf-8")
        .replace("{layer}", layer)
        .replace("{layer_rubric}", layer_rubric)
    )

    prior_line = (
        f"Prior week score: {prior_score}"
        if prior_score is not None
        else "Prior week score: none (first run)"
    )
    signal_lines = "\n".join(
        f"{s.get('importance', 0.0):.2f}  {s.get('summary', '').strip()}  —  {s.get('url', '')}"
        for s in signals
    )
    user_text = (
        f"ISO week: {iso_week}\n"
        f"{prior_line}\n\n"
        f"Signals ({len(signals)} total):\n{signal_lines}"
    )

    tool_schema = {
        "type": "object",
        "properties": {
            "score":              {"type": "integer", "minimum": 1, "maximum": 5},
            "confidence":         {"type": "number",  "minimum": 0.0, "maximum": 1.0},
            "rationale":          {"type": "string"},
            "leading_indicators": {"type": "array", "items": {"type": "string"}},
            "evidence_urls":      {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "confidence", "rationale", "leading_indicators", "evidence_urls"],
    }

    result = _call_tool(
        model=MODEL_SCORE,
        system_text=system_text,
        user_text=user_text,
        tool_name="score_layer",
        tool_description=(
            f"Return the bottleneck severity score and supporting evidence for "
            f"the {layer} layer."
        ),
        tool_schema=tool_schema,
        operation=f"score_bottleneck:{layer}",
        run_id=run_id,
        max_tokens=2048,
    )

    # Validate evidence URLs against the input signal set
    allowed_urls = {s["url"] for s in signals if s.get("url")}
    result["evidence_urls"] = [
        url for url in result.get("evidence_urls", [])
        if url in allowed_urls
    ]

    return result


def score_adoption(
    industry: str,
    iso_week: str,
    prior_score: Optional[int],
    signals: list[dict],
    run_id: Optional[int] = None,
) -> dict:
    """
    Score one industry's AI agent adoption momentum on a 1–5 scale plus
    seven structural factor scores.

    Args:
        industry:    one of INDUSTRIES (e.g. "legal", "software_eng")
        iso_week:    current ISO week string
        prior_score: last week's momentum score for this industry, or None
        signals:     classified signal dicts from DB
        run_id:      optional run ID for logging

    Returns:
        dict with keys: momentum_score, confidence, factors (dict of 7 ints),
                        rationale, evidence_urls
    """
    system_text = (PROMPTS_DIR / "score_adoption.txt").read_text(encoding="utf-8")

    prior_line = (
        f"Prior week momentum score: {prior_score}"
        if prior_score is not None
        else "Prior week momentum score: none (first run)"
    )
    signal_lines = "\n".join(
        f"{s.get('importance', 0.0):.2f}  {s.get('summary', '').strip()}  —  {s.get('url', '')}"
        for s in signals
    )
    user_text = (
        f"Industry: {industry}\n"
        f"ISO week: {iso_week}\n"
        f"{prior_line}\n\n"
        f"Signals ({len(signals)} total):\n{signal_lines}"
    )

    factor_schema = {
        "type": "object",
        "properties": {
            factor: {"type": "integer", "minimum": 1, "maximum": 5}
            for factor in [
                "labor_cost", "workflow_repetitiveness", "digital_artifact",
                "error_cost", "regulatory_burden", "verification_feasibility",
                "tool_api_access",
            ]
        },
        "required": [
            "labor_cost", "workflow_repetitiveness", "digital_artifact",
            "error_cost", "regulatory_burden", "verification_feasibility",
            "tool_api_access",
        ],
    }

    tool_schema = {
        "type": "object",
        "properties": {
            "momentum_score": {"type": "integer", "minimum": 1, "maximum": 5},
            "confidence":     {"type": "number",  "minimum": 0.0, "maximum": 1.0},
            "factors":        factor_schema,
            "rationale":      {"type": "string"},
            "evidence_urls":  {"type": "array", "items": {"type": "string"}},
        },
        "required": ["momentum_score", "confidence", "factors", "rationale", "evidence_urls"],
    }

    result = _call_tool(
        model=MODEL_SCORE,
        system_text=system_text,
        user_text=user_text,
        tool_name="score_industry",
        tool_description=(
            f"Return the agent adoption momentum score and structural factors for "
            f"the {industry} industry."
        ),
        tool_schema=tool_schema,
        operation=f"score_adoption:{industry}",
        run_id=run_id,
        max_tokens=2048,
    )

    # Validate evidence URLs against the input signal set
    allowed_urls = {s["url"] for s in signals if s.get("url")}
    result["evidence_urls"] = [
        url for url in result.get("evidence_urls", [])
        if url in allowed_urls
    ]

    return result


def synthesize_memo(
    iso_week: str,
    bottleneck_scores: list[dict],
    adoption_scores: list[dict],
    top_signals: list[dict],
    run_id: Optional[int] = None,
) -> dict:
    """
    Synthesize the weekly AI intelligence memo from scores and signals.

    Args:
        iso_week:          current ISO week string
        bottleneck_scores: list of dicts from db.get_bottleneck_scores(run_id)
        adoption_scores:   list of dicts from db.get_adoption_scores(run_id)
        top_signals:       list of high-importance signal dicts to cite
        run_id:            optional run ID for logging

    Returns:
        dict with keys: strongest_signal, most_fragile_bottleneck,
                        investable_basket, solo_project, falsification_test,
                        full_markdown
    """
    system_text = (PROMPTS_DIR / "synth_memo.txt").read_text(encoding="utf-8")

    # Format bottleneck scores
    bn_lines = "\n".join(
        f"  {s.get('layer','?'):12s}  score={s.get('score','?')}  "
        f"conf={s.get('confidence',0):.2f}  {s.get('rationale','')[:120]}"
        for s in bottleneck_scores
    )

    # Format adoption scores
    ad_lines = "\n".join(
        f"  {s.get('industry','?'):20s}  momentum={s.get('momentum_score','?')}  "
        f"conf={s.get('confidence',0):.2f}  {s.get('rationale','')[:120]}"
        for s in adoption_scores
    )

    # Format top signals
    sig_lines = "\n".join(
        f"{s.get('importance', 0.0):.2f}  {s.get('summary', '').strip()}  —  {s.get('url', '')}"
        for s in top_signals
    )

    user_text = (
        f"ISO week: {iso_week}\n\n"
        f"BOTTLENECK SCORES:\n{bn_lines}\n\n"
        f"ADOPTION SCORES:\n{ad_lines}\n\n"
        f"TOP SIGNALS ({len(top_signals)} total):\n{sig_lines}"
    )

    tool_schema = {
        "type": "object",
        "properties": {
            "strongest_signal":        {"type": "string"},
            "most_fragile_bottleneck": {"type": "string"},
            "investable_basket":       {"type": "string"},
            "solo_project":            {"type": "string"},
            "falsification_test":      {"type": "string"},
            "full_markdown":           {"type": "string"},
        },
        "required": [
            "strongest_signal", "most_fragile_bottleneck", "investable_basket",
            "solo_project", "falsification_test", "full_markdown",
        ],
    }

    result = _call_tool(
        model=MODEL_MEMO,
        system_text=system_text,
        user_text=user_text,
        tool_name="write_memo",
        tool_description=(
            "Write the complete weekly AI intelligence memo with all five required sections."
        ),
        tool_schema=tool_schema,
        operation="synthesize_memo",
        run_id=run_id,
        max_tokens=8192,
    )

    return result
