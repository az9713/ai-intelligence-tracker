import json
import os
import time
from dataclasses import asdict

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

import src.db as db
from config import CACHE_DIR, PERPLEXITY_BASE_URL, PERPLEXITY_MODEL
from src.models import PerplexityResult
from src.utils import sha256, today_str, utcnow

_COST_PER_CALL = 0.005


def _should_retry(exc: BaseException) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and (exc.response.status_code == 429 or exc.response.status_code >= 500)
    )


def _cache_path(q: str, system_prompt: str | None) -> object:
    key = q + (system_prompt or "") + today_str()
    return CACHE_DIR / f"perplexity_{sha256(key)}.json"


def _load_cache(path) -> PerplexityResult | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PerplexityResult(**data)
    except Exception:
        return None


def _save_cache(path, result: PerplexityResult) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), ensure_ascii=False), encoding="utf-8")


@retry(
    retry=retry_if_exception(_should_retry),
    wait=wait_exponential(min=2, max=60),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _call_api(q: str, system_prompt: str | None) -> tuple[str, list[str]]:
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY is not set")

    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt or "Be precise and cite sources."},
            {"role": "user", "content": q},
        ],
        "return_citations": True,
        "temperature": 0.1,
    }

    response = httpx.post(
        f"{PERPLEXITY_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()

    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response from Perplexity: {response.text[:200]}") from exc

    content = body["choices"][0]["message"]["content"]
    citations = body.get("citations", [])
    return content, citations


def query(
    q: str,
    run_id: int | None = None,
    system_prompt: str | None = None,
) -> PerplexityResult:
    cache_path = _cache_path(q, system_prompt)
    cached = _load_cache(cache_path)
    if cached is not None:
        return cached

    t0 = time.monotonic()
    error_msg: str | None = None
    succeeded = False

    try:
        content, citations = _call_api(q, system_prompt)
        succeeded = True
    except Exception as exc:
        error_msg = str(exc)
        db.log_api_call(
            run_id=run_id,
            provider="perplexity",
            operation="query",
            duration_ms=int((time.monotonic() - t0) * 1000),
            succeeded=False,
            model=PERPLEXITY_MODEL,
            cost_usd=None,
            error=error_msg,
        )
        raise

    duration_ms = int((time.monotonic() - t0) * 1000)
    db.log_api_call(
        run_id=run_id,
        provider="perplexity",
        operation="query",
        duration_ms=duration_ms,
        succeeded=succeeded,
        model=PERPLEXITY_MODEL,
        cost_usd=_COST_PER_CALL,
        error=error_msg,
    )

    result = PerplexityResult(
        query=q,
        content=content,
        citations=citations,
        fetched_at=utcnow(),
    )
    _save_cache(cache_path, result)
    return result
