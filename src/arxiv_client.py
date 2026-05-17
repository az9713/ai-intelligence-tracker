import json
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

import src.db as db
from config import ARXIV_BASE_URL, CACHE_DIR
from src.models import ArxivResult
from src.utils import sha256, today_str, utcnow

_ATOM_NS = "http://www.w3.org/2005/Atom"


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError))


def _cache_path(query: str, max_results: int):
    key = query + str(max_results) + today_str()
    return CACHE_DIR / f"arxiv_{sha256(key)}.json"


def _load_cache(path) -> list[ArxivResult] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [ArxivResult(**item) for item in raw]
    except Exception:
        return None


def _save_cache(path, results: list[ArxivResult]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False),
        encoding="utf-8",
    )


def _parse_feed(xml_bytes: bytes) -> list[ArxivResult]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise RuntimeError(f"Failed to parse arXiv Atom feed: {exc}") from exc

    results: list[ArxivResult] = []
    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        title_el = entry.find(f"{{{_ATOM_NS}}}title")
        abstract_el = entry.find(f"{{{_ATOM_NS}}}summary")
        published_el = entry.find(f"{{{_ATOM_NS}}}published")
        id_el = entry.find(f"{{{_ATOM_NS}}}id")

        title = (title_el.text or "").strip() if title_el is not None else ""
        abstract = (abstract_el.text or "").strip() if abstract_el is not None else ""
        published = (published_el.text or "").strip() if published_el is not None else ""
        url = (id_el.text or "").strip() if id_el is not None else ""

        authors = [
            name_el.text.strip()
            for author in entry.findall(f"{{{_ATOM_NS}}}author")
            if (name_el := author.find(f"{{{_ATOM_NS}}}name")) is not None
            and name_el.text
        ]

        results.append(ArxivResult(
            title=title,
            abstract=abstract,
            url=url,
            authors=authors,
            published=published,
        ))

    return results


@retry(
    retry=retry_if_exception(_should_retry),
    wait=wait_exponential(min=2, max=60),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _call_api(query: str, max_results: int) -> bytes:
    response = httpx.get(
        ARXIV_BASE_URL,
        params={
            "search_query": query,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.content


def search(
    query: str,
    max_results: int = 10,
    run_id: int | None = None,
) -> list[ArxivResult]:
    cache_path = _cache_path(query, max_results)
    cached = _load_cache(cache_path)
    if cached is not None:
        return cached

    t0 = time.monotonic()
    error_msg: str | None = None
    succeeded = False

    try:
        xml_bytes = _call_api(query, max_results)
        results = _parse_feed(xml_bytes)
        succeeded = True
    except Exception as exc:
        error_msg = str(exc)
        db.log_api_call(
            run_id=run_id,
            provider="arxiv",
            operation="search",
            duration_ms=int((time.monotonic() - t0) * 1000),
            succeeded=False,
            cost_usd=0.0,
            error=error_msg,
        )
        raise

    duration_ms = int((time.monotonic() - t0) * 1000)
    db.log_api_call(
        run_id=run_id,
        provider="arxiv",
        operation="search",
        duration_ms=duration_ms,
        succeeded=succeeded,
        cost_usd=0.0,
        error=error_msg,
    )

    _save_cache(cache_path, results)
    return results
