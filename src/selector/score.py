"""한 사이클에서 어떤 클러스터로 글을 쓸지 선정.

스코어 = 소스다양성·신선도·클러스터크기·카테고리다양성 보너스 − 발행이력 페널티.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import timedelta

from src.cluster.merge import TopicCluster
from src.cluster.simhash import hamming
from src.config_loader import load_categories
from src.logging_setup import get_logger
from src.state.db import connect
from src.state.repo import published_recently
from src.utils.timeutil import now_seoul

log = get_logger("selector")


def _category_24h_count() -> Counter:
    cats: Counter = Counter()
    with connect() as conn:
        since = (now_seoul() - timedelta(hours=24)).isoformat()
        rows = conn.execute(
            "SELECT category FROM published WHERE published_at >= ?", (since,)
        ).fetchall()
    for r in rows:
        cats[r["category"]] += 1
    return cats


def _is_recent_duplicate(simhash: int, days: int = 7, max_hamming: int = 3) -> bool:
    with connect() as conn:
        rows = published_recently(conn, days=days)
    for r in rows:
        try:
            if hamming(int(r["cluster_simhash"]), simhash) <= max_hamming:
                return True
        except (TypeError, ValueError):
            continue
    return False


def score(cluster: TopicCluster, category_counts: Counter) -> float:
    diversity = cluster.source_diversity
    size = len(cluster.items)
    freshness = 1.0
    if cluster.latest_published:
        hrs = (now_seoul() - cluster.latest_published).total_seconds() / 3600.0
        freshness = math.exp(-hrs / 24.0)
    cat_pen = 0.0
    diversity_cap = (load_categories().get("diversity") or {}).get("max_per_24h", 3)
    if category_counts.get(cluster.category, 0) >= diversity_cap:
        cat_pen = 1.0
    s = (
        diversity * 0.40
        + math.log1p(size) * 0.20
        + freshness * 0.30
        + 0.10  # base
        - cat_pen
    )
    return s


def pick_topic(clusters: list[TopicCluster]) -> TopicCluster | None:
    if not clusters:
        return None
    cat_counts = _category_24h_count()
    candidates: list[tuple[float, TopicCluster]] = []
    for c in clusters:
        if _is_recent_duplicate(c.simhash):
            log.info("selector.dropped_duplicate", title=c.event_title, simhash=c.simhash)
            continue
        candidates.append((score(c, cat_counts), c))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    top_score, top = candidates[0]
    log.info("selector.picked", title=top.event_title, category=top.category, score=top_score)
    return top
