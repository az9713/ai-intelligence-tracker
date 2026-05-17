"""
scorer.py — Scores all layers and industries using classified signals.

Dispatches to score_all_layers / score_all_industries based on the
track/layer/industry arguments, matching the same filter logic used in
researcher.py.
"""

import logging
from typing import Optional

import src.db as db
import src.claude_client as claude_client
from config import (
    INDUSTRIES,
    LAYERS,
    MODEL_SCORE,
)
from src.models import AdoptionScore, BottleneckScore
from src.utils import iso_week, utcnow

logger = logging.getLogger(__name__)


def score_all_layers(
    run_id: int,
    layers: Optional[list[str]] = None,
) -> None:
    """
    Score each infrastructure bottleneck layer.

    Args:
        run_id: Active run ID.
        layers: Subset of LAYERS to score; defaults to all.
    """
    target_layers = layers if layers is not None else LAYERS

    for layer in target_layers:
        logger.info("Scoring layer=%s", layer)

        signals = db.get_signals_for_scoring(run_id, layer, min_relevance=0.3)
        logger.info(
            "layer=%s  signals_found=%d (min_relevance=0.3)",
            layer, len(signals),
        )

        prior: Optional[int] = db.prior_bottleneck_score(layer, run_id)

        result = claude_client.score_bottleneck(
            layer=layer,
            iso_week=iso_week(),
            prior_score=prior,
            signals=signals,
            run_id=run_id,
        )

        score: int = int(result["score"])
        score_delta: Optional[float] = float(score - prior) if prior is not None else None

        bs = BottleneckScore(
            run_id=run_id,
            layer=layer,
            score=score,
            confidence=float(result.get("confidence", 0.5)),
            rationale=str(result.get("rationale", "")),
            leading_indicators=list(result.get("leading_indicators", [])),
            evidence_urls=list(result.get("evidence_urls", [])),
            model_id=MODEL_SCORE,
            created_at=utcnow(),
            score_delta=score_delta,
        )
        db.upsert_bottleneck_score(bs)

        logger.info(
            "Scored layer=%s  score=%d  delta=%s  confidence=%.2f",
            layer, score,
            f"{score_delta:+.1f}" if score_delta is not None else "n/a",
            bs.confidence,
        )


def score_all_industries(
    run_id: int,
    industries: Optional[list[str]] = None,
) -> None:
    """
    Score each industry's agent adoption momentum.

    Args:
        run_id:     Active run ID.
        industries: Subset of INDUSTRIES to score; defaults to all.
    """
    target_industries = industries if industries is not None else INDUSTRIES

    for industry in target_industries:
        logger.info("Scoring industry=%s", industry)

        # Industry-specific signals + cross-cutting agent signals
        industry_signals = db.get_signals_for_scoring(run_id, industry, min_relevance=0.3)
        cross_signals = db.get_signals_for_scoring(run_id, "cross", min_relevance=0.3)

        # Deduplicate by url_hash (industry signals take precedence)
        seen_hashes: set[str] = set()
        combined_signals: list[dict] = []
        for sig in industry_signals:
            h = sig.get("url_hash", "")
            if h not in seen_hashes:
                seen_hashes.add(h)
                combined_signals.append(sig)
        for sig in cross_signals:
            h = sig.get("url_hash", "")
            if h not in seen_hashes:
                seen_hashes.add(h)
                combined_signals.append(sig)

        logger.info(
            "industry=%s  industry_signals=%d  cross_signals=%d  combined=%d",
            industry, len(industry_signals), len(cross_signals), len(combined_signals),
        )

        prior: Optional[int] = db.prior_adoption_score(industry, run_id)

        result = claude_client.score_adoption(
            industry=industry,
            iso_week=iso_week(),
            prior_score=prior,
            signals=combined_signals,
            run_id=run_id,
        )

        momentum_score: int = int(result["momentum_score"])
        score_delta: Optional[float] = (
            float(momentum_score - prior) if prior is not None else None
        )

        # Extract per-factor scores from the nested `factors` dict
        factors: dict = result.get("factors", {})

        ads = AdoptionScore(
            run_id=run_id,
            industry=industry,
            momentum_score=momentum_score,
            confidence=float(result.get("confidence", 0.5)),
            rationale=str(result.get("rationale", "")),
            evidence_urls=list(result.get("evidence_urls", [])),
            model_id=MODEL_SCORE,
            created_at=utcnow(),
            score_delta=score_delta,
            # Map each factor from the `factors` sub-dict; fall back to neutral 3
            labor_cost=int(factors.get("labor_cost", 3)),
            workflow_repetitiveness=int(factors.get("workflow_repetitiveness", 3)),
            digital_artifact=int(factors.get("digital_artifact", 3)),
            error_cost=int(factors.get("error_cost", 3)),
            regulatory_burden=int(factors.get("regulatory_burden", 3)),
            verification_feasibility=int(factors.get("verification_feasibility", 3)),
            tool_api_access=int(factors.get("tool_api_access", 3)),
        )
        db.upsert_adoption_score(ads)

        logger.info(
            "Scored industry=%s  momentum=%d  delta=%s  confidence=%.2f",
            industry, momentum_score,
            f"{score_delta:+.1f}" if score_delta is not None else "n/a",
            ads.confidence,
        )


def run_scoring(
    run_id: int,
    track: str = "all",
    layer: str | None = None,
    industry: str | None = None,
) -> None:
    """
    Dispatch scoring based on track/layer/industry filters.

    Args:
        run_id:   Active run ID.
        track:    "all" | "bottleneck" | "adoption"
        layer:    If set, score only this layer (implies bottleneck track).
        industry: If set, score only this industry (implies adoption track).
    """
    logger.info(
        "run_scoring started  run_id=%d  track=%s  layer=%s  industry=%s",
        run_id, track, layer, industry,
    )

    run_layers = track in ("all", "bottleneck")
    run_industries = track in ("all", "adoption")

    if run_layers:
        layers_to_score = [layer] if layer is not None else None
        score_all_layers(run_id, layers=layers_to_score)

    if run_industries:
        industries_to_score = [industry] if industry is not None else None
        score_all_industries(run_id, industries=industries_to_score)

    logger.info("run_scoring complete  run_id=%d", run_id)
