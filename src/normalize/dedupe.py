"""1차 디둡 — URL canonicalize + 제목 normalize 후 해시 기반."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse

from src.normalize.item import NormalizedItem

_TRACKERS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}
_TITLE_NORMALIZE = re.compile(r"\s+")


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url)
        query = "&".join(q for q in p.query.split("&") if q and q.split("=")[0] not in _TRACKERS)
        return urlunparse(p._replace(query=query, fragment=""))
    except Exception:
        return url


def _title_key(title: str) -> str:
    return _TITLE_NORMALIZE.sub(" ", title.strip().lower())


def _hash(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def dedupe(items: list[NormalizedItem]) -> list[NormalizedItem]:
    """URL 또는 제목이 같은 항목을 하나로. 더 많은 본문을 가진 쪽 유지."""
    seen: dict[str, NormalizedItem] = {}
    for it in items:
        keys = [_hash(canonical_url(it.url)), _hash(_title_key(it.title))]
        existing = next((seen[k] for k in keys if k in seen), None)
        if existing is None:
            for k in keys:
                seen[k] = it
            continue
        # 이미 같은 항목이 있으면 본문이 더 풍부한 쪽으로 교체
        if len(it.body) > len(existing.body):
            for k in keys:
                seen[k] = it
    # set 순서 보존 위해 id 기준 dedupe
    out: list[NormalizedItem] = []
    seen_ids: set[int] = set()
    for v in seen.values():
        if id(v) in seen_ids:
            continue
        out.append(v)
        seen_ids.add(id(v))
    return out
