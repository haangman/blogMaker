"""한 사이클에서 어떤 클러스터로 글을 쓸지 선정.

V3: 다중 선정(pick_topics) + 일상 토픽 우선 + 중복 윈도우 확장.

스코어 = 소스다양성·신선도·클러스터크기·라이프스타일 보너스 − 카테고리 페널티.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import timedelta

from src.cluster.merge import TopicCluster
from src.cluster.simhash import hamming
from src.config_loader import get_settings, load_categories
from src.logging_setup import get_logger
from src.state.db import connect
from src.state.repo import published_recently
from src.utils.timeutil import now_seoul

log = get_logger("selector")


# 소스별 "일상 토픽 친화도" — 0(완전 기술/전문) ~ 1(완전 일상)
# 일상 토픽 우선을 위해 selector 점수에 가중치로 들어간다.
SOURCE_LIFESTYLE: dict[str, float] = {
    "hackernews":       0.10,
    "lobsters":         0.10,
    "bbc":              0.45,
    "google_news_en":   0.50,
    "reddit_worldnews": 0.55,
    "google_news_ko":   0.65,
    "korean_news":      0.85,
    "reddit_popular":   0.90,
}
_LIFESTYLE_DEFAULT = 0.40


# 같은 사이클 안에서 두 클러스터가 시각적으로 너무 비슷하지 않게 가드.
# simhash 64bit 에서 5 이하면 거의 같은 사건으로 본다.
IN_CYCLE_SIMHASH_GAP = 5


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


def is_recent_duplicate(simhash: int, *, days: int | None = None, max_hamming: int = 3) -> bool:
    """발행 이력 안에서 simhash 매치 검사. days 기본은 settings.duplicate_window_days."""
    if days is None:
        days = get_settings().duplicate_window_days
    with connect() as conn:
        rows = published_recently(conn, days=days)
    for r in rows:
        try:
            if hamming(int(r["cluster_simhash"]), simhash) <= max_hamming:
                return True
        except (TypeError, ValueError):
            continue
    return False


# 하위 호환 alias (기존 호출자 보호)
_is_recent_duplicate = is_recent_duplicate


def _lifestyle_bonus(cluster: TopicCluster) -> float:
    if not cluster.items:
        return 0.0
    s = sum(SOURCE_LIFESTYLE.get(it.source_id, _LIFESTYLE_DEFAULT) for it in cluster.items)
    return s / len(cluster.items)


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

    lifestyle = _lifestyle_bonus(cluster)

    s = (
        diversity * 0.30
        + math.log1p(size) * 0.20
        + freshness * 0.25
        + lifestyle * 0.25
        - cat_pen
    )
    return s


def pick_topics(clusters: list[TopicCluster], n: int = 5) -> list[TopicCluster]:
    """점수 상위 + 중복 가드 + in-cycle 시각적 분리로 N개 후보를 고른다."""
    if not clusters:
        return []
    cat_counts = _category_24h_count()
    settings = get_settings()

    scored: list[tuple[float, TopicCluster]] = []
    for c in clusters:
        if is_recent_duplicate(c.simhash, days=settings.duplicate_window_days):
            log.info("selector.dropped_duplicate",
                     title=c.event_title, simhash=c.simhash,
                     window_days=settings.duplicate_window_days)
            continue
        scored.append((score(c, cat_counts), c))
    if not scored:
        return []
    scored.sort(key=lambda t: -t[0])

    picked: list[TopicCluster] = []
    for sc, c in scored:
        if any(hamming(c.simhash, p.simhash) <= IN_CYCLE_SIMHASH_GAP for p in picked):
            continue
        picked.append(c)
        log.info("selector.picked",
                 idx=len(picked), title=c.event_title,
                 category=c.category, score=round(sc, 3),
                 sources=c.source_diversity, size=len(c.items),
                 lifestyle=round(_lifestyle_bonus(c), 2))
        if len(picked) >= n:
            break
    return picked


def pick_topic(clusters: list[TopicCluster]) -> TopicCluster | None:
    """하위 호환 — 1개만 필요할 때."""
    topics = pick_topics(clusters, n=1)
    return topics[0] if topics else None
