import json
import logging
import time
from pathlib import Path

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

import src.db as db
from config import CACHE_DIR
from src.models import PerplexityResult
from src.utils import sha256, today_str, utcnow

logger = logging.getLogger(__name__)

_SLEEP_BETWEEN_QUERIES = 1.5


def _cache_path(q: str) -> Path:
    key = sha256(f"ddg_{q}_{today_str()}")
    return CACHE_DIR / f"{key}.json"


def _load_cache(q: str) -> PerplexityResult | None:
    p = _cache_path(q)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return PerplexityResult(**data)
        except Exception:
            pass
    return None


def _save_cache(q: str, result: PerplexityResult) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(q).write_text(
        json.dumps(result.__dict__), encoding="utf-8"
    )


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _ddg_search(q: str, max_results: int = 10) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        return list(ddgs.text(q, max_results=max_results))


def query(
    q: str,
    run_id: int | None = None,
    system_prompt: str | None = None,
) -> PerplexityResult:
    cached = _load_cache(q)
    if cached:
        logger.debug("DDG cache hit: %r", q)
        return cached

    t0 = time.monotonic()
    succeeded = False
    error_msg = None
    result = None

    try:
        time.sleep(_SLEEP_BETWEEN_QUERIES)
        hits = _ddg_search(q)
        succeeded = True

        citations = [h["href"] for h in hits if h.get("href")]
        lines = [
            f"**{h.get('title', '')}** — {h.get('body', '')}"
            for h in hits
            if h.get("body")
        ]
        content = "\n\n".join(lines)

        result = PerplexityResult(
            query=q,
            content=content,
            citations=citations,
            fetched_at=utcnow(),
        )
        _save_cache(q, result)

    except Exception as exc:
        error_msg = str(exc)
        logger.warning("DDG query failed for %r: %s", q, exc)
        result = PerplexityResult(query=q, content="", citations=[], fetched_at=utcnow())

    finally:
        duration_ms = int((time.monotonic() - t0) * 1000)
        db.log_api_call(
            run_id=run_id,
            provider="perplexity",  # reuse provider slot; logged as operation="ddg_query"
            operation="ddg_query",
            duration_ms=duration_ms,
            succeeded=succeeded,
            cost_usd=0.0,
            error=error_msg,
        )

    return result
