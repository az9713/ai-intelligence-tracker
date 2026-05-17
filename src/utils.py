import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_week(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%G-W%V")


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lstrip("www.")
    except Exception:
        return ""


def normalize_url(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
    except Exception:
        return url
