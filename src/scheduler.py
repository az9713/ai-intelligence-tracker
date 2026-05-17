"""APScheduler configuration for the AI Intelligence Tracking System.

Three scheduled jobs:
  1. Research  — Mon-Thu 09:00: fetch raw signals
  2. Score     — Thu 18:00:   score bottleneck + adoption layers
  3. Memo      — Fri 09:00:   synthesise weekly memo

All times are local server time. Jobs are wrapped in try/except so a single
failure does not silently kill future fires.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from src.utils import iso_week, today_str, utcnow

logger = logging.getLogger(__name__)

# Module-level singleton so start_scheduler() is idempotent across reloads
scheduler = BackgroundScheduler()


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------

def _job_research() -> None:
    """Mon–Thu 09:00: collect raw signals for the current week."""
    # Import here to avoid circular imports (src.app → src.scheduler → src.researcher)
    from src.researcher import run_research
    import src.db as db

    week = iso_week()
    logger.info("[scheduler] research job fired for week %s", week)

    try:
        existing_id = db.run_exists_for_week(week)

        if existing_id is not None:
            run = db.get_run(existing_id)
            if run and run.get("status") == "completed":
                logger.info(
                    "[scheduler] research: run %d for %s already completed — skipping",
                    existing_id, week,
                )
                return
            # Reuse existing run (INSERT OR IGNORE on signals deduplicates)
            run_id = existing_id
            logger.info(
                "[scheduler] research: reusing existing run %d (status=%s)",
                run_id, run.get("status") if run else "unknown",
            )
        else:
            run_id = db.create_run(today_str(), week, utcnow())
            logger.info("[scheduler] research: created new run %d for %s", run_id, week)

        db.update_run(run_id, stage="research", status="running")
        run_research(run_id, track="all")
        # Leave status=running so the score job can pick it up
        db.update_run(run_id, stage=None)
        logger.info("[scheduler] research: run %d finished fetching signals", run_id)

    except Exception as exc:
        logger.exception("[scheduler] research job failed: %s", exc)


def _job_score() -> None:
    """Thu 18:00: score bottleneck + adoption for the current week's run."""
    # Import here to avoid circular imports
    from src.scorer import run_scoring
    import src.db as db

    week = iso_week()
    logger.info("[scheduler] score job fired for week %s", week)

    try:
        existing_id = db.run_exists_for_week(week)
        if existing_id is None:
            logger.info(
                "[scheduler] score: no run found for %s — skipping", week
            )
            return

        run = db.get_run(existing_id)
        if run is None:
            logger.warning("[scheduler] score: run %d disappeared — skipping", existing_id)
            return

        status = run.get("status")
        if status == "completed":
            logger.info(
                "[scheduler] score: run %d for %s already completed — skipping",
                existing_id, week,
            )
            return
        if status == "failed":
            logger.warning(
                "[scheduler] score: run %d for %s is in failed state — skipping",
                existing_id, week,
            )
            return

        run_id = existing_id
        db.update_run(run_id, stage="score", status="running")
        run_scoring(run_id, track="all")
        db.update_run(run_id, stage=None)
        logger.info("[scheduler] score: run %d scoring finished", run_id)

    except Exception as exc:
        logger.exception("[scheduler] score job failed: %s", exc)


def _job_memo() -> None:
    """Fri 09:00: synthesise the weekly memo for the current week's completed run."""
    # Import here to avoid circular imports
    from src.memo import run_memo
    import src.db as db

    week = iso_week()
    logger.info("[scheduler] memo job fired for week %s", week)

    try:
        # Skip if memo already exists for this week
        existing_memo = db.get_memo(week)
        if existing_memo is not None:
            logger.info(
                "[scheduler] memo: memo for %s already exists — skipping", week
            )
            return

        existing_id = db.run_exists_for_week(week)
        if existing_id is None:
            logger.info(
                "[scheduler] memo: no run found for %s — skipping", week
            )
            return

        run = db.get_run(existing_id)
        if run is None:
            logger.warning("[scheduler] memo: run %d disappeared — skipping", existing_id)
            return

        status = run.get("status")
        if status == "failed":
            logger.warning(
                "[scheduler] memo: run %d is in failed state — skipping", existing_id
            )
            return

        # Run memo even if status is still "running" (scores may already be written)
        run_id = existing_id
        db.update_run(run_id, stage="memo")
        run_memo(run_id)
        db.update_run(run_id, status="completed", stage=None, completed_at=utcnow())
        logger.info("[scheduler] memo: run %d memo written and marked completed", run_id)

    except Exception as exc:
        logger.exception("[scheduler] memo job failed: %s", exc)


# ---------------------------------------------------------------------------
# Scheduler startup
# ---------------------------------------------------------------------------

def start_scheduler(app=None) -> None:
    """Add cron jobs and start the APScheduler BackgroundScheduler.

    Safe to call multiple times — guards against double-start via
    scheduler.running check on the module-level singleton.

    Args:
        app: Optional Flask app instance (reserved for future app-context use).
    """
    if scheduler.running:
        logger.debug("[scheduler] already running — skipping start")
        return

    # --- Research: Mon, Tue, Wed, Thu at 09:00 ---
    scheduler.add_job(
        func=_job_research,
        trigger="cron",
        day_of_week="mon,tue,wed,thu",
        hour=9,
        minute=0,
        id="research",
        replace_existing=True,
        misfire_grace_time=3600,  # 1 hour grace window
    )

    # --- Score: Thu at 18:00 ---
    scheduler.add_job(
        func=_job_score,
        trigger="cron",
        day_of_week="thu",
        hour=18,
        minute=0,
        id="score",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # --- Memo: Fri at 09:00 ---
    scheduler.add_job(
        func=_job_memo,
        trigger="cron",
        day_of_week="fri",
        hour=9,
        minute=0,
        id="memo",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info(
        "[scheduler] started with jobs: %s",
        [job.id for job in scheduler.get_jobs()],
    )
