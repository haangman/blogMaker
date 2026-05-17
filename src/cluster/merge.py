"""클러스터별 사건 통합 요약 + 카테고리 분류 + simhash 산출."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from src.categorize.classify import classify_category
from src.cluster.embed import embed
from src.cluster.hdbscan_cluster import cluster_items
from src.cluster.simhash import simhash64
from src.config_loader import get_settings
from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger
from src.normalize.item import NormalizedItem

log = get_logger("cluster.merge")


@dataclass
class TopicCluster:
    items: list[NormalizedItem]
    event_title: str
    event_summary: str
    category: str           # categories.yaml 의 id
    simhash: int
    embedding: np.ndarray | None = None
    score_extra: dict = field(default_factory=dict)

    @property
    def source_diversity(self) -> int:
        return len({it.source_id for it in self.items})

    @property
    def latest_published(self) -> datetime | None:
        ts = [it.published_at for it in self.items if it.published_at]
        return max(ts) if ts else None


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
        resp = ask(user, system_prompt=_MERGE_SYSTEM, model="sonnet", purpose="cluster_merge")
    except ClaudeCLIError as e:
        log.warning("cluster.merge_llm_failed", error=str(e))
        # 폴백: 대표 항목 1개의 제목/리드
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


def cluster_and_merge(items: list[NormalizedItem]) -> list[TopicCluster]:
    """전체 normalize 결과를 클러스터링하고 각 클러스터의 사건 요약/카테고리/simhash 계산."""
    groups = cluster_items(items)
    log.info("cluster.groups", n=len(groups))
    if not groups:
        return []

    # 요약 텍스트만 모아 벡터 계산을 한 번에
    titles_and_summaries: list[tuple[list[NormalizedItem], str, str]] = []
    for grp in groups:
        title, summary = _merge_with_llm(grp)
        titles_and_summaries.append((grp, title, summary))

    summaries = [s for (_, _, s) in titles_and_summaries]
    vecs = embed(summaries) if summaries else np.zeros((0, 384), dtype=np.float32)

    clusters: list[TopicCluster] = []
    for idx, (grp, title, summary) in enumerate(titles_and_summaries):
        cat = classify_category(title, summary)
        clusters.append(
            TopicCluster(
                items=grp,
                event_title=title,
                event_summary=summary,
                category=cat,
                simhash=simhash64(summary),
                embedding=vecs[idx] if vecs.shape[0] else None,
            )
        )
    return clusters
