"""클러스터링 + (선정 이후) 사건 통합 요약 + 카테고리 분류.

비용 보호 — cluster_only 단계에서는 LLM 을 한 번도 부르지 않는다.
selector 가 후보 1개를 고른 다음, enrich_with_llm 으로 그 1개만 LLM 처리한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from src.categorize.classify import classify_category
from src.cluster.embed import embed
from src.cluster.hdbscan_cluster import cluster_items
from src.cluster.simhash import simhash64
from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger
from src.normalize.item import NormalizedItem

log = get_logger("cluster.merge")


@dataclass
class TopicCluster:
    items: list[NormalizedItem]
    event_title: str
    event_summary: str
    category: str           # categories.yaml 의 id. enrich 전에는 'other' 기본.
    simhash: int
    embedding: np.ndarray | None = None
    enriched: bool = False
    score_extra: dict = field(default_factory=dict)

    @property
    def source_diversity(self) -> int:
        return len({it.source_id for it in self.items})

    @property
    def latest_published(self) -> datetime | None:
        ts = [it.published_at for it in self.items if it.published_at]
        return max(ts) if ts else None


def _provisional_title(items: list[NormalizedItem]) -> str:
    """가장 본문이 풍부한 항목의 제목을 임시 대표 제목으로."""
    if not items:
        return ""
    best = max(items, key=lambda it: len(it.body) + len(it.title))
    return best.title[:80]


def _provisional_summary(items: list[NormalizedItem]) -> str:
    if not items:
        return ""
    parts: list[str] = []
    for it in items[:3]:
        if it.body:
            parts.append(it.body[:240])
        elif it.title:
            parts.append(it.title)
    return " / ".join(parts)[:600]


def cluster_only(items: list[NormalizedItem]) -> list[TopicCluster]:
    """LLM 없이 클러스터링 + 가벼운 메타만 채워서 후보 반환."""
    groups = cluster_items(items)
    log.info("cluster.groups", n=len(groups))
    if not groups:
        return []

    # 임베딩: 그룹 대표 텍스트
    rep_texts = [
        " ".join([(g[0].title or ""), ((g[0].body or "")[:200])]).strip() or "untitled"
        for g in groups
    ]
    vecs = embed(rep_texts) if rep_texts else np.zeros((0, 384), dtype=np.float32)

    clusters: list[TopicCluster] = []
    for idx, grp in enumerate(groups):
        title = _provisional_title(grp)
        summary = _provisional_summary(grp)
        clusters.append(
            TopicCluster(
                items=grp,
                event_title=title,
                event_summary=summary,
                category="other",                # enrich 전 기본
                simhash=simhash64(title + " " + summary),
                embedding=vecs[idx] if vecs.shape[0] else None,
                enriched=False,
            )
        )
    return clusters


_MERGE_SYSTEM = (
    "여러 뉴스 항목을 받아서 같은 사건을 하나의 통합 요약으로 정리한다. "
    "출력 형식은 반드시 다음과 같이 두 줄로만:\n"
    "TITLE: <한국어 12자 이내 사건 제목>\n"
    "SUMMARY: <한국어 2~3문장. 사건의 핵심·맥락·왜 화제인지. 의견·감탄·수사 금지.>"
)


def _merge_with_llm(items: list[NormalizedItem]) -> tuple[str, str]:
    bullets = []
    for it in items[:8]:
        line = f"- ({it.source_id}/{it.lang}) {it.title}"
        if it.body:
            line += f" | {it.body[:200].strip()}"
        bullets.append(line)
    user = "다음 항목들을 통합:\n" + "\n".join(bullets)
    try:
        resp = ask(user, system_prompt=_MERGE_SYSTEM, model="opus", purpose="cluster_merge")
    except ClaudeCLIError as e:
        log.warning("cluster.merge_llm_failed", error=str(e))
        rep = items[0]
        return rep.title[:60], (rep.body or rep.title)[:300]

    title, summary = "", ""
    for line in resp.text.splitlines():
        if line.upper().startswith("TITLE:"):
            title = line.split(":", 1)[1].strip()
        elif line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
    if not title:
        title = items[0].title[:60]
    if not summary:
        summary = resp.text.strip()[:300]
    return title, summary


def enrich_with_llm(cluster: TopicCluster, *, categories_file: str = "categories.yaml") -> TopicCluster:
    """선정된 클러스터 1개를 LLM 으로 통합 요약 + 카테고리 분류 + simhash 재계산."""
    if cluster.enriched:
        return cluster
    title, summary = _merge_with_llm(cluster.items)
    cat = classify_category(title, summary, categories_file=categories_file)
    cluster.event_title = title
    cluster.event_summary = summary
    cluster.category = cat
    cluster.simhash = simhash64(title + " " + summary)
    cluster.enriched = True
    log.info("cluster.enriched", title=title, category=cat, simhash=cluster.simhash)
    return cluster
