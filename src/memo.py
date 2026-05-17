"""
memo.py — Generates the weekly Friday synthesis memo.

Loads scored data for the run, selects top signals, calls Claude to
synthesize a memo, persists it to DB, and writes the Markdown file.
"""

import logging

import src.db as db
import src.claude_client as claude_client
from config import MEMOS_DIR, MODEL_MEMO
from src.models import Memo
from src.utils import iso_week, utcnow

logger = logging.getLogger(__name__)

# Minimum relevance for signals included in memo context
_MEMO_MIN_RELEVANCE = 0.5

# Number of top signals to pass to Claude
_MEMO_TOP_N = 15


def run_memo(run_id: int) -> None:
    """
    Synthesize and persist the weekly intelligence memo.

    Steps:
      1. Load bottleneck and adoption scores for this run.
      2. Select top signals by importance (relevance >= 0.5, limit 15).
      3. Call Claude to synthesize the memo.
      4. Persist the Memo dataclass to DB.
      5. Write full_markdown to MEMOS_DIR/<iso_week>.md.

    Args:
        run_id: Active run ID whose scores and signals to use.
    """
    logger.info("run_memo started  run_id=%d", run_id)

    # Step 1: load scores
    bottleneck_scores = db.get_bottleneck_scores(run_id)
    adoption_scores = db.get_adoption_scores(run_id)
    logger.info(
        "Loaded %d bottleneck scores and %d adoption scores",
        len(bottleneck_scores), len(adoption_scores),
    )

    # Step 2: top signals ordered by importance, relevance >= 0.5
    top_signals = db.list_signals(
        run_id=run_id,
        min_relevance=_MEMO_MIN_RELEVANCE,
        limit=_MEMO_TOP_N,
    )
    logger.info("Top signals for memo: %d", len(top_signals))

    # Step 3: synthesize via Claude
    week = iso_week()
    result = claude_client.synthesize_memo(
        iso_week=week,
        bottleneck_scores=bottleneck_scores,
        adoption_scores=adoption_scores,
        top_signals=top_signals,
        run_id=run_id,
    )

    # Step 4: persist to DB
    memo = Memo(
        run_id=run_id,
        iso_week=week,
        strongest_signal=str(result.get("strongest_signal", "")),
        most_fragile_bottleneck=str(result.get("most_fragile_bottleneck", "")),
        investable_basket=str(result.get("investable_basket", "")),
        solo_project=str(result.get("solo_project", "")),
        falsification_test=str(result.get("falsification_test", "")),
        full_markdown=str(result.get("full_markdown", "")),
        model_id=MODEL_MEMO,
        created_at=utcnow(),
    )
    db.upsert_memo(memo)
    logger.info("Memo persisted to DB  iso_week=%s", week)

    # Step 5: write Markdown file
    MEMOS_DIR.mkdir(parents=True, exist_ok=True)
    memo_path = MEMOS_DIR / f"{week}.md"
    memo_path.write_text(memo.full_markdown, encoding="utf-8")
    logger.info("Memo written to %s", memo_path)

    logger.info("run_memo complete  run_id=%d  iso_week=%s", run_id, week)
