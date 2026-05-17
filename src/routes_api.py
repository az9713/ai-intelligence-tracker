"""Flask Blueprint with all API endpoints for the AI Intelligence Tracking System."""

import logging
import threading
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request

from config import DB_PATH, LAYERS, INDUSTRIES
from src.db import (
    list_runs,
    get_run,
    latest_completed_run,
    get_bottleneck_scores,
    get_bottleneck_history,
    get_adoption_scores,
    get_adoption_history,
    get_latest_memo,
    get_memo,
    list_memos,
    list_signals,
    get_costs,
    create_run,
    update_run,
    run_exists_for_week,
)
from src.utils import iso_week, today_str, utcnow

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)

# Mapping of run stage to progress percentage
_STAGE_PROGRESS = {
    "research": 25,
    "score": 75,
    "memo": 95,
}


# ---------------------------------------------------------------------------
# Background pipeline thread
# ---------------------------------------------------------------------------

def _run_pipeline(run_id: int, track: str) -> None:
    """Execute the full research → scoring → memo pipeline in a background thread."""
    # Import inside function to avoid circular imports at module load time
    from src.researcher import run_research
    from src.scorer import run_scoring
    from src.memo import run_memo

    try:
        update_run(run_id, stage="research")
        run_research(run_id, track=track)

        update_run(run_id, stage="score")
        run_scoring(run_id, track=track)

        update_run(run_id, stage="memo")
        run_memo(run_id)

        update_run(run_id, status="completed", stage=None, completed_at=utcnow())
        logger.info("Pipeline run_id=%d completed successfully", run_id)
    except Exception as exc:
        logger.exception("Pipeline run_id=%d failed: %s", run_id, exc)
        update_run(run_id, status="failed", error=str(exc))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@api_bp.route("/health")
def health():
    """Return system health information."""
    run = latest_completed_run()
    return jsonify({
        "status": "ok",
        "db_exists": DB_PATH.exists(),
        "last_run_id": run["id"] if run else None,
        "last_run_date": run["run_date"] if run else None,
        "last_run_status": run["status"] if run else None,
        "iso_week": iso_week(),
    })


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@api_bp.route("/runs")
def get_runs():
    """List recent runs."""
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        return jsonify({"error": "limit must be an integer"}), 400

    runs = list_runs(limit=limit)
    return jsonify(runs)


@api_bp.route("/runs/<int:run_id>")
def get_run_by_id(run_id: int):
    """Get a single run by ID."""
    run = get_run(run_id)
    if run is None:
        return jsonify({"error": f"Run {run_id} not found"}), 404
    return jsonify(run)


@api_bp.route("/run/trigger", methods=["POST"])
def trigger_run():
    """Trigger a new pipeline run in the background.

    Accepts optional JSON body: {"track": "all" | "bottleneck" | "adoption"}
    Returns 202 with the new run_id and iso_week.
    Returns 409 if a run for the current week already exists.
    """
    body = request.get_json(silent=True) or {}
    track = body.get("track", "all")
    if track not in ("all", "bottleneck", "adoption"):
        return jsonify({"error": "track must be 'all', 'bottleneck', or 'adoption'"}), 400

    week = iso_week()
    existing_id = run_exists_for_week(week)
    if existing_id is not None:
        existing = get_run(existing_id)
        # Return 409 with information about the existing run
        return jsonify({
            "error": f"A run for week {week} already exists",
            "run_id": existing_id,
            "status": existing.get("status") if existing else None,
            "iso_week": week,
        }), 409

    run_id = create_run(today_str(), week, utcnow())
    logger.info("Triggered pipeline run_id=%d track=%s week=%s", run_id, track, week)

    t = threading.Thread(target=_run_pipeline, args=(run_id, track), daemon=True)
    t.start()

    return jsonify({"run_id": run_id, "iso_week": week}), 202


@api_bp.route("/run/<int:run_id>/status")
def get_run_status(run_id: int):
    """Get status and progress for a specific run."""
    run = get_run(run_id)
    if run is None:
        return jsonify({"error": f"Run {run_id} not found"}), 404

    status = run.get("status")
    stage = run.get("stage")

    if status == "completed":
        progress_pct = 100
    elif status == "failed":
        progress_pct = 0
    else:
        progress_pct = _STAGE_PROGRESS.get(stage, 0) if stage else 0

    return jsonify({
        "run_id": run_id,
        "status": status,
        "stage": stage,
        "progress_pct": progress_pct,
    })


# ---------------------------------------------------------------------------
# Bottleneck
# ---------------------------------------------------------------------------

@api_bp.route("/bottleneck/latest")
def bottleneck_latest():
    """Return bottleneck scores for the latest completed run."""
    run = latest_completed_run()
    if run is None:
        return jsonify({"error": "No completed run available"}), 404

    scores = get_bottleneck_scores(run["id"])
    return jsonify({
        "run_id": run["id"],
        "iso_week": run["iso_week"],
        "scores": scores,
    })


@api_bp.route("/bottleneck/history")
def bottleneck_history():
    """Return score history for a bottleneck layer."""
    layer = request.args.get("layer")
    if not layer:
        return jsonify({"error": "layer parameter is required"}), 400
    if layer not in LAYERS:
        return jsonify({"error": f"Unknown layer '{layer}'. Valid layers: {', '.join(LAYERS)}"}), 400

    try:
        weeks = int(request.args.get("weeks", 12))
    except (TypeError, ValueError):
        return jsonify({"error": "weeks must be an integer"}), 400

    history = get_bottleneck_history(layer, weeks=weeks)
    return jsonify({"layer": layer, "history": history})


@api_bp.route("/bottleneck/<layer>/evidence")
def bottleneck_evidence(layer: str):
    """Return score details and top signals for a bottleneck layer."""
    if layer not in LAYERS:
        return jsonify({"error": f"Unknown layer '{layer}'. Valid layers: {', '.join(LAYERS)}"}), 400

    run_id_param = request.args.get("run_id")
    if run_id_param is not None:
        try:
            run_id = int(run_id_param)
        except (TypeError, ValueError):
            return jsonify({"error": "run_id must be an integer"}), 400
        run = get_run(run_id)
        if run is None:
            return jsonify({"error": f"Run {run_id} not found"}), 404
    else:
        run = latest_completed_run()
        if run is None:
            return jsonify({"error": "No completed run available"}), 404
        run_id = run["id"]

    # Find the score row for this specific layer
    all_scores = get_bottleneck_scores(run_id)
    score_row = next((s for s in all_scores if s["layer"] == layer), None)

    # Fetch top 10 signals for this layer/category
    signals = list_signals(run_id=run_id, category=layer, limit=10)

    return jsonify({
        "layer": layer,
        "score_row": score_row,
        "signals": signals,
    })


# ---------------------------------------------------------------------------
# Adoption
# ---------------------------------------------------------------------------

@api_bp.route("/adoption/latest")
def adoption_latest():
    """Return adoption scores for the latest completed run."""
    run = latest_completed_run()
    if run is None:
        return jsonify({"error": "No completed run available"}), 404

    scores = get_adoption_scores(run["id"])
    return jsonify({
        "run_id": run["id"],
        "iso_week": run["iso_week"],
        "scores": scores,
    })


@api_bp.route("/adoption/history")
def adoption_history():
    """Return momentum score history for an industry."""
    industry = request.args.get("industry")
    if not industry:
        return jsonify({"error": "industry parameter is required"}), 400
    if industry not in INDUSTRIES:
        return jsonify({"error": f"Unknown industry '{industry}'. Valid industries: {', '.join(INDUSTRIES)}"}), 400

    try:
        weeks = int(request.args.get("weeks", 12))
    except (TypeError, ValueError):
        return jsonify({"error": "weeks must be an integer"}), 400

    history = get_adoption_history(industry, weeks=weeks)
    return jsonify({"industry": industry, "history": history})


@api_bp.route("/adoption/<industry>/evidence")
def adoption_evidence(industry: str):
    """Return score details and top signals for an industry."""
    if industry not in INDUSTRIES:
        return jsonify({"error": f"Unknown industry '{industry}'. Valid industries: {', '.join(INDUSTRIES)}"}), 400

    run_id_param = request.args.get("run_id")
    if run_id_param is not None:
        try:
            run_id = int(run_id_param)
        except (TypeError, ValueError):
            return jsonify({"error": "run_id must be an integer"}), 400
        run = get_run(run_id)
        if run is None:
            return jsonify({"error": f"Run {run_id} not found"}), 404
    else:
        run = latest_completed_run()
        if run is None:
            return jsonify({"error": "No completed run available"}), 404
        run_id = run["id"]

    # Find the score row for this specific industry
    all_scores = get_adoption_scores(run_id)
    score_row = next((s for s in all_scores if s["industry"] == industry), None)

    # Fetch top signals: industry-specific + cross-cutting
    industry_signals = list_signals(run_id=run_id, category=industry, limit=10)
    cross_signals = list_signals(run_id=run_id, track="cross", limit=10)

    # Merge and deduplicate by id, preserving importance order, capped at 10
    seen_ids = set()
    combined = []
    for sig in industry_signals + cross_signals:
        sig_id = sig.get("id")
        if sig_id not in seen_ids:
            seen_ids.add(sig_id)
            combined.append(sig)
        if len(combined) >= 10:
            break

    return jsonify({
        "industry": industry,
        "score_row": score_row,
        "signals": combined,
    })


# ---------------------------------------------------------------------------
# Memos
# ---------------------------------------------------------------------------

@api_bp.route("/memo/latest")
def memo_latest():
    """Return the most recent intelligence memo."""
    memo = get_latest_memo()
    if memo is None:
        return jsonify({"error": "No memo available"}), 404
    return jsonify(memo)


@api_bp.route("/memo")
def memo_by_week():
    """Return a memo for a specific ISO week (e.g. ?week=2026-W20)."""
    week = request.args.get("week")
    if not week:
        return jsonify({"error": "week parameter is required (e.g. 2026-W20)"}), 400

    memo = get_memo(week)
    if memo is None:
        return jsonify({"error": f"No memo found for week {week}"}), 404
    return jsonify(memo)


@api_bp.route("/memos")
def list_all_memos():
    """Return summary list of all memos."""
    memos = list_memos()
    return jsonify(memos)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

@api_bp.route("/signals")
def get_signals():
    """Return filtered raw signals with pagination.

    Query params: run_id, track, category, min_relevance, limit, offset
    """
    run_id_param = request.args.get("run_id")
    run_id = None
    if run_id_param:
        try:
            run_id = int(run_id_param)
        except (TypeError, ValueError):
            return jsonify({"error": "run_id must be an integer"}), 400

    track = request.args.get("track") or None
    category = request.args.get("category") or None

    try:
        min_relevance = float(request.args.get("min_relevance", 0.0))
    except (TypeError, ValueError):
        return jsonify({"error": "min_relevance must be a float"}), 400

    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        return jsonify({"error": "limit must be an integer"}), 400

    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "offset must be an integer"}), 400

    signals = list_signals(
        run_id=run_id,
        track=track,
        category=category,
        min_relevance=min_relevance,
        limit=limit,
        offset=offset,
    )

    return jsonify({"signals": signals, "total_shown": len(signals)})


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------

@api_bp.route("/costs")
def get_api_costs():
    """Return API cost breakdown since a given date.

    Query param: since (YYYY-MM-DD). Defaults to 30 days ago.
    """
    since = request.args.get("since")
    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    costs = get_costs(since)
    return jsonify(costs)
