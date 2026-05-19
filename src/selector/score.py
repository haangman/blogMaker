"""한 사이클에서 어떤 클러스터로 글을 쓸지 선정.

V3: 다중 선정(pick_topics) + 일상 토픽 우선 + 중복 윈도우 확장.

스코어 = 소스다양성·신선도·클러스터크기·라이프스타일 보너스 − 카테고리 페널티.
"""

from __future__ import annotations

import math
import re
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

# 패션·뷰티 블로그(fashion) selector 가중치
SOURCE_FASHION_RELEVANCE: dict[str, float] = {
    "vogue":                  0.95,
    "allure":                 0.95,
    "elle":                   0.90,
    "refinery29":             0.90,
    "fashionbiz":             0.90,
    "google_news_fashion_ko": 0.85,
    "google_news_fashion_en": 0.85,
    "reddit_femalefashion":   0.85,
    "reddit_malefashion":     0.80,
    "reddit_makeupaddiction": 0.85,
    "reddit_skincareaddiction": 0.85,
    "reddit_fashion":         0.80,
}
_FASHION_DEFAULT = 0.30


_PROFILE_WEIGHTS: dict[str, tuple[dict[str, float], float]] = {
    "lifestyle": (SOURCE_LIFESTYLE, _LIFESTYLE_DEFAULT),
    "ai":        (SOURCE_AI_RELEVANCE, _AI_DEFAULT),
    "fashion":   (SOURCE_FASHION_RELEVANCE, _FASHION_DEFAULT),
}


# 같은 사이클 안에서 두 클러스터가 시각적으로 너무 비슷하지 않게 가드.
# simhash 64bit 에서 5 이하면 거의 같은 사건으로 본다.
IN_CYCLE_SIMHASH_GAP = 5

# 제목 정규화된 토큰 자카드 임계. simhash 가 흔들려도 제목이 같은 사건이면
# 잡아내기 위한 보조 가드 — in-cycle 중복 + 발행 이력 중복 둘 다 사용.
# 0.5 = 토큰 절반 이상 겹치면 같은 사건.
IN_CYCLE_TITLE_JACCARD = 0.5
RECENT_TITLE_JACCARD = 0.5   # 사용자 결정: 30일 이력과의 자카드 임계도 0.5 (어제와 같은 사건이 다른 측면으로 또 발행되는 패턴 차단)


_STOPWORDS = {
    # 한국어 조사·일반 단어 + 영어 stop words — 자카드 노이즈 줄임
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만",
    "the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "at",
    "is", "are", "was", "were", "be", "been", "with", "by", "from",
}

# 토큰 끝에 붙은 한국어 조사를 떼어낸다. 긴 조사부터 시도해서 정확히 매칭.
# 예: "드레스코드와" → "드레스코드", "월드컵을" → "월드컵", "모스크바권에서" → "모스크바권"
_KO_PARTICLES = (
    "에서", "으로", "에게", "에서는", "에서도", "라는", "하고",
    "와의", "과의", "와는", "과는",
    "와", "과", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로",
)


def _strip_korean_particle(token: str) -> str:
    if not token:
        return token
    # 한글로 끝나는 토큰에만 적용 (영어/숫자 토큰은 보존)
    if not ("가" <= token[-1] <= "힣"):
        return token
    for p in _KO_PARTICLES:
        if len(token) >= len(p) + 2 and token.endswith(p):
            return token[: -len(p)]
    return token


def _title_norm(title: str) -> set[str]:
    """제목을 정규화된 토큰 집합으로.
    소문자 + 특수문자 제거 + stop words 제거 + 한국어 조사 절단.
    토큰 길이 2 이상만 유지 (1글자 토큰은 노이즈)."""
    if not title:
        return set()
    cleaned = re.sub(r"[^\w가-힣\s]+", " ", title.lower())
    out: set[str] = set()
    for t in cleaned.split():
        if not t or t in _STOPWORDS:
            continue
        t = _strip_korean_particle(t)
        if len(t) >= 2 and t not in _STOPWORDS:
            out.add(t)
    return out


def _title_jaccard(t1: str, t2: str) -> float:
    s1, s2 = _title_norm(t1), _title_norm(t2)
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def _max_title_jaccard(title: str, others: list[str]) -> float:
    """주어진 제목과 others 리스트 중 가장 높은 자카드 값."""
    if not title or not others:
        return 0.0
    s = _title_norm(title)
    if not s:
        return 0.0
    best = 0.0
    for o in others:
        s2 = _title_norm(o)
        if not s2:
            continue
        j = len(s & s2) / len(s | s2)
        if j > best:
            best = j
    return best


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
    title: str | None = None,
    title_jaccard_threshold: float = RECENT_TITLE_JACCARD,
) -> bool:
    """발행 이력 안에서 simhash · 임베딩 코사인 · 제목 토큰 자카드 매치 검사.

    cluster_merge 가 같은 사건에 다른 제목/요약을 만들 때 simhash·임베딩이
    모두 흔들릴 수 있어, 정규화된 제목 토큰 자카드를 세 번째 신호로 추가.
    셋 중 하나라도 매치되면 중복.
    """
    if days is None:
        days = get_settings().duplicate_window_days
    since = (now_seoul() - timedelta(days=days)).isoformat()
    with connect() as conn:
        if blog_id:
            rows = conn.execute(
                "SELECT cluster_simhash, cluster_embedding, title FROM published "
                "WHERE published_at >= ? AND blog_id = ?",
                (since, blog_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT cluster_simhash, cluster_embedding, title FROM published "
                "WHERE published_at >= ?",
                (since,),
            ).fetchall()

    q_norm: np.ndarray | None = None
    if embedding is not None and embedding.size:
        q_norm = embedding / (np.linalg.norm(embedding) + 1e-9)

    title_tokens = _title_norm(title) if title else None

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
        # 3) 제목 토큰 자카드 — simhash·임베딩이 흔들려도 같은 제목이면 잡힘
        if title_tokens:
            other_tokens = _title_norm(r["title"] or "")
            if other_tokens:
                jac = len(title_tokens & other_tokens) / len(title_tokens | other_tokens)
                if jac >= title_jaccard_threshold:
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
            title=c.event_title,
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
        # 제목 자카드 가드 — simhash 가 흔들려도 정규화된 제목이 비슷하면 skip
        max_jac = _max_title_jaccard(c.event_title, [p.event_title for p in picked])
        if max_jac >= IN_CYCLE_TITLE_JACCARD:
            log.info("selector.skip_in_cycle_title_dup",
                     title=c.event_title, max_jaccard=round(max_jac, 2),
                     blog=blog_id)
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
