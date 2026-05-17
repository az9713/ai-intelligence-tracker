import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from config import DB_PATH
from src.models import (
    AdoptionScore, BottleneckScore, Memo, RawSignal, Run,
)

_DDL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date      TEXT    NOT NULL,
    iso_week      TEXT    NOT NULL,
    started_at    TEXT    NOT NULL,
    completed_at  TEXT,
    status        TEXT    NOT NULL CHECK(status IN ('running','completed','failed','partial')),
    stage         TEXT,
    error         TEXT,
    UNIQUE(iso_week)
);

CREATE TABLE IF NOT EXISTS raw_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL,
    track           TEXT    NOT NULL CHECK(track IN ('bottleneck','adoption','cross')),
    category        TEXT    NOT NULL,
    signal_type     TEXT    NOT NULL,
    query           TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    url_hash        TEXT    NOT NULL,
    title           TEXT,
    snippet         TEXT,
    source_domain   TEXT,
    published_at    TEXT,
    fetched_at      TEXT    NOT NULL,
    relevance       REAL    DEFAULT 0,
    importance      REAL    DEFAULT 0,
    summary         TEXT    DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
    UNIQUE(run_id, url_hash, signal_type)
);
CREATE INDEX IF NOT EXISTS idx_raw_run_category ON raw_signals(run_id, category);
CREATE INDEX IF NOT EXISTS idx_raw_signal_type  ON raw_signals(signal_type);

CREATE TABLE IF NOT EXISTS bottleneck_scores (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               INTEGER NOT NULL,
    layer                TEXT    NOT NULL CHECK(layer IN
        ('gpu','hbm','networking','dc_shell','power','cooling','fab')),
    score                INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
    score_delta          REAL,
    confidence           REAL    NOT NULL,
    rationale            TEXT    NOT NULL,
    leading_indicators   TEXT    NOT NULL,
    evidence_urls        TEXT    NOT NULL,
    model_id             TEXT    NOT NULL,
    created_at           TEXT    NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
    UNIQUE(run_id, layer)
);

CREATE TABLE IF NOT EXISTS adoption_scores (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   INTEGER NOT NULL,
    industry                 TEXT    NOT NULL CHECK(industry IN
        ('software_eng','legal','accounting','insurance','healthcare_admin',
         'finance_ops','marketing','customer_support','manufacturing','defense_aero')),
    momentum_score           INTEGER NOT NULL CHECK(momentum_score BETWEEN 1 AND 5),
    score_delta              REAL,
    labor_cost               INTEGER NOT NULL CHECK(labor_cost BETWEEN 1 AND 5),
    workflow_repetitiveness  INTEGER NOT NULL CHECK(workflow_repetitiveness BETWEEN 1 AND 5),
    digital_artifact         INTEGER NOT NULL CHECK(digital_artifact BETWEEN 1 AND 5),
    error_cost               INTEGER NOT NULL CHECK(error_cost BETWEEN 1 AND 5),
    regulatory_burden        INTEGER NOT NULL CHECK(regulatory_burden BETWEEN 1 AND 5),
    verification_feasibility INTEGER NOT NULL CHECK(verification_feasibility BETWEEN 1 AND 5),
    tool_api_access          INTEGER NOT NULL CHECK(tool_api_access BETWEEN 1 AND 5),
    confidence               REAL    NOT NULL,
    rationale                TEXT    NOT NULL,
    evidence_urls            TEXT    NOT NULL,
    model_id                 TEXT    NOT NULL,
    created_at               TEXT    NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
    UNIQUE(run_id, industry)
);

CREATE TABLE IF NOT EXISTS memos (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   INTEGER NOT NULL,
    iso_week                 TEXT    NOT NULL,
    strongest_signal         TEXT    NOT NULL,
    most_fragile_bottleneck  TEXT    NOT NULL,
    investable_basket        TEXT    NOT NULL,
    solo_project             TEXT    NOT NULL,
    falsification_test       TEXT    NOT NULL,
    full_markdown            TEXT    NOT NULL,
    model_id                 TEXT    NOT NULL,
    created_at               TEXT    NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
    UNIQUE(iso_week)
);

CREATE TABLE IF NOT EXISTS api_calls (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER,
    provider       TEXT NOT NULL CHECK(provider IN ('anthropic','perplexity','arxiv')),
    operation      TEXT NOT NULL,
    model          TEXT,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    cache_read     INTEGER,
    cache_write    INTEGER,
    duration_ms    INTEGER NOT NULL,
    cost_usd       REAL,
    succeeded      INTEGER NOT NULL,
    error          TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_api_created ON api_calls(created_at);

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_meta(key, value) VALUES('schema_version', '1');
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema():
    with get_conn() as conn:
        conn.executescript(_DDL)


# --- runs ---

def create_run(run_date: str, iso_week: str, started_at: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO runs(run_date, iso_week, started_at, status) VALUES(?,?,?,'running')",
            (run_date, iso_week, started_at),
        )
        return cur.lastrowid


def update_run(run_id: int, **kwargs):
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [run_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE runs SET {fields} WHERE id=?", values)


def get_run(run_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None


def latest_completed_run() -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE status='completed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def list_runs(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def run_exists_for_week(iso_week: str) -> Optional[int]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM runs WHERE iso_week=?", (iso_week,)
        ).fetchone()
        return row["id"] if row else None


def delete_run(run_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM runs WHERE id=?", (run_id,))


# --- raw_signals ---

def insert_raw_signal(sig: RawSignal):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO raw_signals
               (run_id,track,category,signal_type,query,url,url_hash,title,snippet,
                source_domain,published_at,fetched_at,relevance,importance,summary)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sig.run_id, sig.track, sig.category, sig.signal_type, sig.query,
             sig.url, sig.url_hash, sig.title, sig.snippet, sig.source_domain,
             sig.published_at, sig.fetched_at, sig.relevance, sig.importance, sig.summary),
        )


def update_signal_classify(url_hash: str, run_id: int, relevance: float,
                             importance: float, summary: str):
    with get_conn() as conn:
        conn.execute(
            """UPDATE raw_signals SET relevance=?, importance=?, summary=?
               WHERE url_hash=? AND run_id=?""",
            (relevance, importance, summary, url_hash, run_id),
        )


def get_signals_for_scoring(run_id: int, category: str,
                              min_relevance: float = 0.3) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM raw_signals
               WHERE run_id=? AND category=? AND relevance>=?
               ORDER BY importance DESC""",
            (run_id, category, min_relevance),
        ).fetchall()
        return [dict(r) for r in rows]


def list_signals(run_id: Optional[int] = None, track: Optional[str] = None,
                  category: Optional[str] = None, min_relevance: float = 0.0,
                  limit: int = 50, offset: int = 0) -> list[dict]:
    where, params = ["1=1"], []
    if run_id:
        where.append("run_id=?"); params.append(run_id)
    if track:
        where.append("track=?"); params.append(track)
    if category:
        where.append("category=?"); params.append(category)
    if min_relevance > 0:
        where.append("relevance>=?"); params.append(min_relevance)
    params += [limit, offset]
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM raw_signals WHERE {' AND '.join(where)} "
            f"ORDER BY importance DESC, fetched_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


# --- bottleneck_scores ---

def upsert_bottleneck_score(bs: BottleneckScore):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO bottleneck_scores
               (run_id,layer,score,score_delta,confidence,rationale,
                leading_indicators,evidence_urls,model_id,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (bs.run_id, bs.layer, bs.score, bs.score_delta, bs.confidence,
             bs.rationale, json.dumps(bs.leading_indicators),
             json.dumps(bs.evidence_urls), bs.model_id, bs.created_at),
        )


def get_bottleneck_scores(run_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bottleneck_scores WHERE run_id=?", (run_id,)
        ).fetchall()
        return [_parse_json_fields(dict(r), ["leading_indicators", "evidence_urls"])
                for r in rows]


def get_bottleneck_history(layer: str, weeks: int = 12) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT bs.score, bs.score_delta, bs.confidence, r.iso_week
               FROM bottleneck_scores bs JOIN runs r ON bs.run_id=r.id
               WHERE bs.layer=? AND r.status='completed'
               ORDER BY r.id DESC LIMIT ?""",
            (layer, weeks),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def prior_bottleneck_score(layer: str, exclude_run_id: int) -> Optional[int]:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT bs.score FROM bottleneck_scores bs
               JOIN runs r ON bs.run_id=r.id
               WHERE bs.layer=? AND r.status='completed' AND bs.run_id<?
               ORDER BY bs.run_id DESC LIMIT 1""",
            (layer, exclude_run_id),
        ).fetchone()
        return row["score"] if row else None


# --- adoption_scores ---

def upsert_adoption_score(ads: AdoptionScore):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO adoption_scores
               (run_id,industry,momentum_score,score_delta,labor_cost,
                workflow_repetitiveness,digital_artifact,error_cost,regulatory_burden,
                verification_feasibility,tool_api_access,confidence,rationale,
                evidence_urls,model_id,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ads.run_id, ads.industry, ads.momentum_score, ads.score_delta,
             ads.labor_cost, ads.workflow_repetitiveness, ads.digital_artifact,
             ads.error_cost, ads.regulatory_burden, ads.verification_feasibility,
             ads.tool_api_access, ads.confidence, ads.rationale,
             json.dumps(ads.evidence_urls), ads.model_id, ads.created_at),
        )


def get_adoption_scores(run_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM adoption_scores WHERE run_id=?", (run_id,)
        ).fetchall()
        return [_parse_json_fields(dict(r), ["evidence_urls"]) for r in rows]


def get_adoption_history(industry: str, weeks: int = 12) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT ads.momentum_score, ads.score_delta, ads.confidence, r.iso_week
               FROM adoption_scores ads JOIN runs r ON ads.run_id=r.id
               WHERE ads.industry=? AND r.status='completed'
               ORDER BY r.id DESC LIMIT ?""",
            (industry, weeks),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def prior_adoption_score(industry: str, exclude_run_id: int) -> Optional[int]:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT ads.momentum_score FROM adoption_scores ads
               JOIN runs r ON ads.run_id=r.id
               WHERE ads.industry=? AND r.status='completed' AND ads.run_id<?
               ORDER BY ads.run_id DESC LIMIT 1""",
            (industry, exclude_run_id),
        ).fetchone()
        return row["momentum_score"] if row else None


# --- memos ---

def upsert_memo(m: Memo):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO memos
               (run_id,iso_week,strongest_signal,most_fragile_bottleneck,
                investable_basket,solo_project,falsification_test,
                full_markdown,model_id,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (m.run_id, m.iso_week, m.strongest_signal, m.most_fragile_bottleneck,
             m.investable_basket, m.solo_project, m.falsification_test,
             m.full_markdown, m.model_id, m.created_at),
        )


def get_memo(iso_week: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM memos WHERE iso_week=?", (iso_week,)
        ).fetchone()
        return dict(row) if row else None


def get_latest_memo() -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM memos ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def list_memos() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id,iso_week,strongest_signal,created_at FROM memos ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# --- api_calls ---

def log_api_call(run_id: Optional[int], provider: str, operation: str,
                  duration_ms: int, succeeded: bool, model: Optional[str] = None,
                  input_tokens: Optional[int] = None, output_tokens: Optional[int] = None,
                  cache_read: Optional[int] = None, cache_write: Optional[int] = None,
                  cost_usd: Optional[float] = None, error: Optional[str] = None):
    from src.utils import utcnow
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO api_calls
               (run_id,provider,operation,model,input_tokens,output_tokens,
                cache_read,cache_write,duration_ms,cost_usd,succeeded,error,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, provider, operation, model, input_tokens, output_tokens,
             cache_read, cache_write, duration_ms, cost_usd,
             1 if succeeded else 0, error, utcnow()),
        )


def get_costs(since: str) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT operation, SUM(cost_usd) as total, COUNT(*) as calls
               FROM api_calls WHERE created_at>=? AND cost_usd IS NOT NULL
               GROUP BY operation""",
            (since,),
        ).fetchall()
        by_op = {r["operation"]: {"total_usd": r["total"], "calls": r["calls"]}
                 for r in rows}
        total = sum(r["total"] for r in rows if r["total"])
        return {"total_usd": round(total, 6), "by_operation": by_op}


# --- helpers ---

def _parse_json_fields(row: dict, fields: list[str]) -> dict:
    for f in fields:
        if f in row and isinstance(row[f], str):
            try:
                row[f] = json.loads(row[f])
            except Exception:
                row[f] = []
    return row
