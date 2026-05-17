from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Run:
    id: int
    run_date: str
    iso_week: str
    started_at: str
    status: str
    stage: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


@dataclass
class RawSignal:
    run_id: int
    track: str
    category: str
    signal_type: str
    query: str
    url: str
    url_hash: str
    title: str
    snippet: str
    source_domain: str
    fetched_at: str
    relevance: float = 0.0
    importance: float = 0.0
    summary: str = ""
    published_at: Optional[str] = None
    id: Optional[int] = None


@dataclass
class BottleneckScore:
    run_id: int
    layer: str
    score: int
    confidence: float
    rationale: str
    leading_indicators: list[str]
    evidence_urls: list[str]
    model_id: str
    created_at: str
    score_delta: Optional[float] = None
    id: Optional[int] = None


@dataclass
class AdoptionScore:
    run_id: int
    industry: str
    momentum_score: int
    confidence: float
    rationale: str
    evidence_urls: list[str]
    model_id: str
    created_at: str
    labor_cost: int = 3
    workflow_repetitiveness: int = 3
    digital_artifact: int = 3
    error_cost: int = 3
    regulatory_burden: int = 3
    verification_feasibility: int = 3
    tool_api_access: int = 3
    score_delta: Optional[float] = None
    id: Optional[int] = None


@dataclass
class Memo:
    run_id: int
    iso_week: str
    strongest_signal: str
    most_fragile_bottleneck: str
    investable_basket: str
    solo_project: str
    falsification_test: str
    full_markdown: str
    model_id: str
    created_at: str
    id: Optional[int] = None


@dataclass
class PerplexityResult:
    query: str
    content: str
    citations: list[str]
    fetched_at: str


@dataclass
class ArxivResult:
    title: str
    abstract: str
    url: str
    authors: list[str]
    published: str


@dataclass
class ClassifyResult:
    index: int
    is_relevant: bool
    relevance: float
    importance: float
    summary: str
    signal_type: str = ""
