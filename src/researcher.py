"""
researcher.py — Orchestrates research for all signal types.

Fetches signals via Perplexity (all tracks) and arXiv (adoption/cross),
inserts them into raw_signals, then classifies in batches via Claude.
"""

import logging
from datetime import datetime, timezone

import src.db as db
import src.search_client as search_client
import src.arxiv_client as arxiv_client
import src.claude_client as claude_client
from config import (
    ARXIV_QUERIES,
    CROSS_AGENT_SIGNAL_TYPES,
    INDUSTRY_TO_SIGNAL_TYPES,
    LAYER_TO_SIGNAL_TYPES,
    SIGNAL_QUERIES,
)
from src.models import RawSignal
from src.utils import domain, normalize_url, sha256, utcnow

logger = logging.getLogger(__name__)

# Batch size for classify_batch calls
_CLASSIFY_BATCH_SIZE = 10

# signal_type label used for arXiv results
_ARXIV_SIGNAL_TYPE = "arxiv_research"


def _current_year() -> str:
    return str(datetime.now(timezone.utc).year)


def _build_signal_type_map() -> dict[str, tuple[str, str]]:
    """
    Return a mapping of signal_type -> (track, category).

    Layer signal types  -> ("bottleneck", layer_key)
    Industry signal types -> ("adoption", industry_key)
    Cross-cutting types -> ("adoption", "cross")
    """
    mapping: dict[str, tuple[str, str]] = {}

    for layer, signal_types in LAYER_TO_SIGNAL_TYPES.items():
        for st in signal_types:
            mapping[st] = ("bottleneck", layer)

    for signal_type in CROSS_AGENT_SIGNAL_TYPES:
        mapping[signal_type] = ("adoption", "cross")

    for industry, signal_types in INDUSTRY_TO_SIGNAL_TYPES.items():
        for st in signal_types:
            # Cross-cutting types are already registered; only add industry-specific
            if st not in mapping:
                mapping[st] = ("adoption", industry)

    return mapping


def _determine_signal_types(
    track: str,
    layer: str | None,
    industry: str | None,
) -> list[str]:
    """
    Return the list of signal types to fetch based on track/layer/industry filters.
    """
    if track == "bottleneck":
        if layer is not None:
            return list(LAYER_TO_SIGNAL_TYPES.get(layer, []))
        # All bottleneck signal types
        return [st for sts in LAYER_TO_SIGNAL_TYPES.values() for st in sts]

    if track == "adoption":
        if industry is not None:
            # Cross-cutting + this industry's specific signal type
            return CROSS_AGENT_SIGNAL_TYPES + [f"industry_{industry}"]
        # All cross-cutting + all industry-specific
        all_adoption: list[str] = list(CROSS_AGENT_SIGNAL_TYPES)
        for industry_key in INDUSTRY_TO_SIGNAL_TYPES:
            all_adoption.append(f"industry_{industry_key}")
        return all_adoption

    # track == "all"
    all_types: list[str] = []
    for sts in LAYER_TO_SIGNAL_TYPES.values():
        all_types.extend(sts)
    all_types.extend(CROSS_AGENT_SIGNAL_TYPES)
    for industry_key in INDUSTRY_TO_SIGNAL_TYPES:
        all_types.append(f"industry_{industry_key}")
    return all_types


def _should_run_arxiv(track: str, layer: str | None) -> bool:
    """arXiv queries only apply to adoption/cross track, not pure bottleneck runs."""
    if track == "bottleneck":
        return False
    if track == "all" and layer is not None:
        # Restricted to a single layer — skip arXiv
        return False
    return True


def _fetch_perplexity_signals(
    run_id: int,
    signal_types: list[str],
    signal_type_map: dict[str, tuple[str, str]],
) -> list[tuple[str, str, str, str]]:
    """
    Fetch Perplexity results for each signal type and insert raw signals.

    Returns a list of (url_hash, title, snippet, url) tuples for all
    successfully inserted signals (deduplicated by url_hash within this run).
    """
    year = _current_year()
    inserted: list[tuple[str, str, str, str]] = []
    seen_hashes: set[str] = set()

    for signal_type in signal_types:
        queries = SIGNAL_QUERIES.get(signal_type)
        if not queries:
            logger.warning("No queries configured for signal_type=%s, skipping", signal_type)
            continue

        track, category = signal_type_map.get(signal_type, ("adoption", "cross"))
        logger.info(
            "Researching signal_type=%s  track=%s  category=%s  queries=%d",
            signal_type, track, category, len(queries),
        )

        for raw_query in queries:
            q = raw_query.replace("{YYYY}", year)
            result = search_client.query(q, run_id=run_id)

            for url in result.citations:
                if not url:
                    continue

                url_hash = sha256(normalize_url(url))
                title = f"{signal_type} signal"
                snippet = result.content[:500]

                sig = RawSignal(
                    run_id=run_id,
                    track=track,
                    category=category,
                    signal_type=signal_type,
                    query=q,
                    url=url,
                    url_hash=url_hash,
                    title=title,
                    snippet=snippet,
                    source_domain=domain(url),
                    fetched_at=result.fetched_at,
                )
                db.insert_raw_signal(sig)

                # Collect for classification (deduplicate within this run)
                if url_hash not in seen_hashes:
                    seen_hashes.add(url_hash)
                    inserted.append((url_hash, title, snippet, url))

    return inserted


def _fetch_arxiv_signals(
    run_id: int,
) -> list[tuple[str, str, str, str]]:
    """
    Fetch arXiv results and insert as raw signals with track="adoption", category="cross".

    Returns a list of (url_hash, title, snippet, url) tuples for all
    successfully inserted signals (deduplicated by url_hash within this run).
    """
    inserted: list[tuple[str, str, str, str]] = []
    seen_hashes: set[str] = set()

    for q in ARXIV_QUERIES:
        logger.info("Fetching arXiv query=%r", q)
        results = arxiv_client.search(q, run_id=run_id)

        for arxiv_result in results:
            url = arxiv_result.url
            if not url:
                continue

            url_hash = sha256(normalize_url(url))
            title = arxiv_result.title or f"{_ARXIV_SIGNAL_TYPE} signal"
            snippet = arxiv_result.abstract[:500] if arxiv_result.abstract else ""

            sig = RawSignal(
                run_id=run_id,
                track="adoption",
                category="cross",
                signal_type=_ARXIV_SIGNAL_TYPE,
                query=q,
                url=url,
                url_hash=url_hash,
                title=title,
                snippet=snippet,
                source_domain=domain(url),
                fetched_at=utcnow(),
                published_at=arxiv_result.published or None,
            )
            db.insert_raw_signal(sig)

            if url_hash not in seen_hashes:
                seen_hashes.add(url_hash)
                inserted.append((url_hash, title, snippet, url))

    return inserted


def _classify_signals(
    run_id: int,
    signals: list[tuple[str, str, str, str]],
) -> None:
    """
    Classify all collected signals in batches of _CLASSIFY_BATCH_SIZE.

    Each element of `signals` is (url_hash, title, snippet, url).
    Updates each signal row via db.update_signal_classify.
    """
    total = len(signals)
    logger.info("Classifying %d signals in batches of %d", total, _CLASSIFY_BATCH_SIZE)

    for batch_start in range(0, total, _CLASSIFY_BATCH_SIZE):
        batch = signals[batch_start: batch_start + _CLASSIFY_BATCH_SIZE]

        # Build items list with in-batch indices (0-based)
        items = [
            {
                "index": i,
                "title": title,
                "snippet": snippet,
                "url": url,
            }
            for i, (url_hash, title, snippet, url) in enumerate(batch)
        ]

        classify_results = claude_client.classify_batch(items, run_id=run_id)

        for cr in classify_results:
            url_hash, _title, _snippet, _url = batch[cr.index]
            db.update_signal_classify(
                url_hash=url_hash,
                run_id=run_id,
                relevance=cr.relevance,
                importance=cr.importance,
                summary=cr.summary,
            )

        logger.info(
            "Classified batch %d-%d of %d",
            batch_start + 1,
            min(batch_start + _CLASSIFY_BATCH_SIZE, total),
            total,
        )


def run_research(
    run_id: int,
    track: str = "all",
    layer: str | None = None,
    industry: str | None = None,
) -> None:
    """
    Orchestrate research for all relevant signal types.

    Args:
        run_id:   Active run ID for DB inserts and API logging.
        track:    "all" | "bottleneck" | "adoption" — which signal families to fetch.
        layer:    If set, restrict bottleneck research to this one layer.
        industry: If set, restrict adoption research to this one industry.
    """
    logger.info(
        "run_research started  run_id=%d  track=%s  layer=%s  industry=%s",
        run_id, track, layer, industry,
    )

    signal_type_map = _build_signal_type_map()
    signal_types = _determine_signal_types(track, layer, industry)

    logger.info(
        "Will fetch %d signal types via %s",
        len(signal_types), search_client.active_provider(),
    )

    # Phase 1: fetch Perplexity signals
    all_inserted = _fetch_perplexity_signals(run_id, signal_types, signal_type_map)

    # Phase 2: fetch arXiv signals (adoption track only)
    if _should_run_arxiv(track, layer):
        logger.info("Fetching arXiv signals (%d queries)", len(ARXIV_QUERIES))
        arxiv_inserted = _fetch_arxiv_signals(run_id)

        # Merge, deduplicating against Perplexity hashes already collected
        perp_hashes = {url_hash for url_hash, *_ in all_inserted}
        for entry in arxiv_inserted:
            if entry[0] not in perp_hashes:
                all_inserted.append(entry)
    else:
        logger.info("Skipping arXiv (track=%s, layer=%s)", track, layer)

    logger.info("Total unique signals collected: %d", len(all_inserted))

    # Phase 3: classify in batches
    _classify_signals(run_id, all_inserted)

    logger.info("run_research complete  run_id=%d", run_id)
