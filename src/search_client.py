"""
Unified search dispatcher. Reads SEARCH_PROVIDER env var (default: duckduckgo).
Switch to Perplexity by setting SEARCH_PROVIDER=perplexity in .env.
"""

import os

from src.models import PerplexityResult


def query(
    q: str,
    run_id: int | None = None,
    system_prompt: str | None = None,
) -> PerplexityResult:
    provider = os.getenv("SEARCH_PROVIDER", "duckduckgo").lower().strip()
    if provider == "perplexity":
        from src.perplexity_client import query as _query
    else:
        from src.ddg_client import query as _query
    return _query(q, run_id=run_id, system_prompt=system_prompt)


def active_provider() -> str:
    return os.getenv("SEARCH_PROVIDER", "duckduckgo").lower().strip()
