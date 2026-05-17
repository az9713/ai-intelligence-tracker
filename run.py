import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from config import (
    CACHE_DIR, DATA_DIR, DB_PATH, LAYERS, INDUSTRIES, LOGS_DIR, MEMOS_DIR,
)


@click.group()
def cli():
    """AI Intelligence Tracking System"""


@cli.command()
def init_db():
    """Create/migrate database schema (idempotent)."""
    from src.db import init_schema
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    MEMOS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    init_schema()
    click.echo(f"Database initialized at {DB_PATH}")


@cli.command()
def doctor():
    """Check environment: API keys, connectivity, DB."""
    import os, httpx, anthropic
    ok = True

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        click.echo("[FAIL] ANTHROPIC_API_KEY not set")
        ok = False
    else:
        try:
            client = anthropic.Anthropic(api_key=anthropic_key)
            client.models.list()
            click.echo("[OK]   Anthropic API reachable")
        except Exception as e:
            click.echo(f"[FAIL] Anthropic API: {e}")
            ok = False

    perplexity_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not perplexity_key:
        click.echo("[FAIL] PERPLEXITY_API_KEY not set")
        ok = False
    else:
        try:
            r = httpx.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {perplexity_key}"},
                json={"model": "sonar-pro", "messages": [{"role": "user", "content": "ping"}]},
                timeout=10,
            )
            r.raise_for_status()
            click.echo("[OK]   Perplexity API reachable")
        except Exception as e:
            click.echo(f"[FAIL] Perplexity API: {e}")
            ok = False

    try:
        import httpx as _httpx
        r = _httpx.get("https://export.arxiv.org/api/query?search_query=AI&max_results=1", timeout=10)
        r.raise_for_status()
        click.echo("[OK]   arXiv API reachable")
    except Exception as e:
        click.echo(f"[FAIL] arXiv API: {e}")
        ok = False

    if DB_PATH.exists():
        click.echo(f"[OK]   DB exists ({DB_PATH.stat().st_size // 1024} KB)")
    else:
        click.echo("[INFO] DB not yet created — run init-db first")

    sys.exit(0 if ok else 1)


@cli.command("run-once")
@click.option("--track", default="all", type=click.Choice(["all", "bottleneck", "adoption"]))
@click.option("--layer", default=None, type=click.Choice(LAYERS))
@click.option("--industry", default=None, type=click.Choice(INDUSTRIES))
@click.option("--skip-memo", is_flag=True)
@click.option("--force", is_flag=True)
def run_once(track, layer, industry, skip_memo, force):
    """Run full pipeline: research → classify → score → memo."""
    from src.researcher import run_research
    from src.scorer import run_scoring
    from src.memo import run_memo
    from src.db import run_exists_for_week, delete_run
    from src.utils import today_str, iso_week, utcnow
    import src.db as db

    week = iso_week()
    existing_id = run_exists_for_week(week)
    if existing_id and not force:
        click.echo(f"Run for {week} already exists (id={existing_id}). Use --force to overwrite.")
        return
    if existing_id and force:
        delete_run(existing_id)
        click.echo(f"Deleted existing run {existing_id} for {week}.")

    run_id = db.create_run(today_str(), week, utcnow())
    click.echo(f"Started run {run_id} for {week}")

    try:
        db.update_run(run_id, stage="research")
        run_research(run_id, track=track, layer=layer, industry=industry)

        db.update_run(run_id, stage="score")
        run_scoring(run_id, track=track, layer=layer, industry=industry)

        if not skip_memo:
            db.update_run(run_id, stage="memo")
            run_memo(run_id)

        db.update_run(run_id, status="completed", stage=None,
                      completed_at=utcnow())
        click.echo(f"Run {run_id} completed.")
    except Exception as e:
        db.update_run(run_id, status="failed", error=str(e))
        click.echo(f"Run {run_id} failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=5000)
@click.option("--no-schedule", is_flag=True)
@click.option("--debug", is_flag=True)
def serve(host, port, no_schedule, debug):
    """Start Flask server (+ optional APScheduler)."""
    from src.app import create_app
    app = create_app(schedule=not no_schedule)
    app.run(host=host, port=port, debug=debug)


@cli.command()
def status():
    """Show last run, current stage, and cost to date."""
    from src.db import latest_completed_run, get_costs, list_runs
    from src.utils import today_str
    from datetime import datetime, timezone, timedelta

    runs = list_runs(limit=3)
    if not runs:
        click.echo("No runs yet.")
        return
    for r in runs:
        click.echo(f"Run {r['id']}  {r['iso_week']}  {r['status']}  stage={r['stage']}")

    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    costs = get_costs(since)
    click.echo(f"\nCost (last 30d): ${costs['total_usd']:.4f}")


@cli.command()
@click.option("--since", default=None)
def costs(since):
    """Show API cost breakdown."""
    from src.db import get_costs
    from datetime import datetime, timezone, timedelta
    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    data = get_costs(since)
    click.echo(f"Total since {since}: ${data['total_usd']:.4f}")
    for op, info in data["by_operation"].items():
        click.echo(f"  {op:30s}  ${info['total_usd']:.4f}  ({info['calls']} calls)")


@cli.command("export-memo")
@click.option("--week", required=True)
@click.option("--out", default=None)
def export_memo(week, out):
    """Export a memo as markdown."""
    from src.db import get_memo
    memo = get_memo(week)
    if not memo:
        click.echo(f"No memo for {week}", err=True)
        sys.exit(1)
    content = memo["full_markdown"]
    if out:
        Path(out).write_text(content, encoding="utf-8")
        click.echo(f"Written to {out}")
    else:
        click.echo(content)


@cli.command("reset-week")
@click.option("--week", required=True)
def reset_week(week):
    """Delete a run and all its data (asks for confirmation)."""
    from src.db import run_exists_for_week, delete_run
    run_id = run_exists_for_week(week)
    if not run_id:
        click.echo(f"No run found for {week}")
        return
    click.confirm(f"Delete run {run_id} for {week} and all its data?", abort=True)
    delete_run(run_id)
    click.echo(f"Deleted run {run_id}.")


if __name__ == "__main__":
    cli()
