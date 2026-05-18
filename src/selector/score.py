"""한 사이클에서 어떤 클러스터로 글을 쓸지 선정.

V3: 다중 선정(pick_topics) + 일상 토픽 우선 + 중복 윈도우 확장.

스코어 = 소스다양성·신선도·클러스터크기·라이프스타일 보너스 − 카테고리 페널티.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import timedelta

import numpy as np

from src.cluster.merge import TopicCluster
from src.cluster.simhash import hamming
from src.config_loader import get_settings, load_categories
from src.logging_setup import get_logger
from src.state.db import connect
from src.state.repo import published_recently
from src.utils.timeutil import now_seoul

# 같은 사건이라도 cluster_merge 가 매번 다른 제목/요약을 만들면 simhash 가 흔들림.
# 임베딩 코사인이 더 안정적이라 simhash 와 함께 가드 — 둘 중 하나라도 매치면 중복.
DUPLICATE_COSINE_THRESHOLD = 0.85


def _decode_embedding(blob: bytes | None) -> np.ndarray | None:
    if not blob:
        return None
    try:
        return np.frombuffer(blob, dtype=np.float32)
    except Exception:
        return None

log = get_logger("selector")


# 소스별 "일상 토픽 친화도" — 0(완전 기술/전문) ~ 1(완전 일상)
# 일상 블로그(trends)의 selector 가중치
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

# AI 기술 블로그(ai)의 selector 가중치 — AI 관련도가 높을수록 +
SOURCE_AI_RELEVANCE: dict[str, float] = {
    "arxiv_cs_ai":        0.95,
    "hf_papers":          0.95,
    "reddit_ml":          0.95,
    "reddit_local_llama": 0.90,
    "reddit_singularity": 0.70,
    "hackernews_ai":      0.55,   # HN 은 AI 토픽이 절반
    "hackernews":         0.35,   # 일반 HN 도 일부 AI
}
_AI_DEFAULT = 0.30


_PROFILE_WEIGHTS: dict[str, tuple[dict[str, float], float]] = {
    "lifestyle": (SOURCE_LIFESTYLE, _LIFESTYLE_DEFAULT),
    "ai":        (SOURCE_AI_RELEVANCE, _AI_DEFAULT),
}


# 같은 사이클 안에서 두 클러스터가 시각적으로 너무 비슷하지 않게 가드.
# simhash 64bit 에서 5 이하면 거의 같은 사건으로 본다.
IN_CYCLE_SIMHASH_GAP = 5


def _category_24h_count(blog_id: str | None = None) -> Counter:
    cats: Counter = Counter()
    with connect() as conn:
        since = (now_seoul() - timedelta(hours=24)).isoformat()
        if blog_id:
            rows = conn.execute(
                "SELECT category FROM published WHERE published_at >= ? AND blog_id = ?",
                (since, blog_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT category FROM published WHERE published_at >= ?", (since,)
            ).fetchall()
    for r in rows:
        cats[r["category"]] += 1
    return cats


def is_recent_duplicate(
    simhash: int,
    *,
    days: int | None = None,
    max_hamming: int = 3,
    blog_id: str | None = None,
    embedding: np.ndarray | None = None,
    cosine_threshold: float = DUPLICATE_COSINE_THRESHOLD,
) -> bool:
    """발행 이력 안에서 simhash 또는 임베딩 코사인 매치 검사.

    simhash 만으로는 cluster_merge 가 매번 다른 제목/요약을 만들 때 흔들리므로,
    임베딩 코사인 (cluster_embedding BLOB) 도 함께 비교한다.
    둘 중 하나라도 매치되면 중복으로 판정.
    """
    if days is None:
        days = get_settings().duplicate_window_days
    since = (now_seoul() - timedelta(days=days)).isoformat()
    with connect() as conn:
        if blog_id:
            rows = conn.execute(
                "SELECT cluster_simhash, cluster_embedding FROM published "
                "WHERE published_at >= ? AND blog_id = ?",
                (since, blog_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT cluster_simhash, cluster_embedding FROM published WHERE published_at >= ?",
                (since,),
            ).fetchall()

    q_norm: np.ndarray | None = None
    if embedding is not None and embedding.size:
        q_norm = embedding / (np.linalg.norm(embedding) + 1e-9)

    for r in rows:
        # 1) simhash
        try:
            if hamming(int(r["cluster_simhash"]), simhash) <= max_hamming:
                return True
        except (TypeError, ValueError):
            pass
        # 2) embedding cosine
        if q_norm is not None:
            v = _decode_embedding(r["cluster_embedding"])
            if v is not None and v.size == q_norm.size:
                v_norm = v / (np.linalg.norm(v) + 1e-9)
                if float(np.dot(q_norm, v_norm)) >= cosine_threshold:
                    return True
    return False


# 하위 호환 alias (기존 호출자 보호)
_is_recent_duplicate = is_recent_duplicate


def _lifestyle_bonus(cluster: TopicCluster) -> float:
    if not cluster.items:
        return 0.0
    s = sum(SOURCE_LIFESTYLE.get(it.source_id, _LIFESTYLE_DEFAULT) for it in cluster.items)
    return s / len(cluster.items)


def _profile_bonus(cluster: TopicCluster, profile: str) -> float:
    if not cluster.items:
        return 0.0
    weights, default = _PROFILE_WEIGHTS.get(profile, (SOURCE_LIFESTYLE, _LIFESTYLE_DEFAULT))
    s = sum(weights.get(it.source_id, default) for it in cluster.items)
    return s / len(cluster.items)


def score(cluster: TopicCluster, category_counts: Counter,
          *, selector_profile: str = "lifestyle") -> float:
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

    profile_score = _profile_bonus(cluster, selector_profile)

    s = (
        diversity * 0.30
        + math.log1p(size) * 0.20
        + freshness * 0.25
        + profile_score * 0.25
        - cat_pen
    )
    return s


def pick_topics(
    clusters: list[TopicCluster],
    n: int = 5,
    *,
    selector_profile: str = "lifestyle",
    blog_id: str | None = None,
) -> list[TopicCluster]:
    """점수 상위 + 중복 가드 + in-cycle 시각적 분리로 N개 후보를 고른다.

    blog_id 가 주어지면 카테고리 분산·중복 가드를 그 블로그 발행 이력으로만 한정.
    """
    if not clusters:
        return []
    cat_counts = _category_24h_count(blog_id=blog_id)
    settings = get_settings()

    scored: list[tuple[float, TopicCluster]] = []
    for c in clusters:
        if is_recent_duplicate(
            c.simhash,
            days=settings.duplicate_window_days,
            blog_id=blog_id,
            embedding=c.embedding,
        ):
            log.info("selector.dropped_duplicate",
                     title=c.event_title, simhash=c.simhash,
                     window_days=settings.duplicate_window_days,
                     blog=blog_id)
            continue
        scored.append((score(c, cat_counts, selector_profile=selector_profile), c))
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
                 profile=selector_profile,
                 profile_bonus=round(_profile_bonus(c, selector_profile), 2))
        if len(picked) >= n:
            break
    return picked


def pick_topic(clusters: list[TopicCluster]) -> TopicCluster | None:
    """하위 호환 — 1개만 필요할 때."""
    topics = pick_topics(clusters, n=1)
    return topics[0] if topics else None
