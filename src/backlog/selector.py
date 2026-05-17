"""백로그 토픽을 사이클당 K편 선정.

priority high > medium > low, 같은 우선순위에선 카테고리 분산, 그 다음 오래된 것 우선.
중복 발행 가드: 발행 이력 simhash 와 매치되면 skip + mark skipped.
"""

from __future__ import annotations

from collections import defaultdict

from src.backlog.loader import BacklogTopic, list_pending
from src.cluster.simhash import hamming, simhash64, to_signed64
from src.logging_setup import get_logger
from src.selector.score import is_recent_duplicate

log = get_logger("backlog.selector")


def pick_backlog_topics(
    blog_id: str,
    n: int,
    *,
    cycle_simhashes: list[int] | None = None,
    in_cycle_gap: int = 5,
) -> list[BacklogTopic]:
    """pending 토픽 중 N개 선정. 중복 가드 + 카테고리 분산."""
    if n <= 0:
        return []
    cycle_simhashes = list(cycle_simhashes or [])
    candidates = list_pending(blog_id, limit=200)
    if not candidates:
        return []

    picked: list[BacklogTopic] = []
    category_count: dict[str, int] = defaultdict(int)

    # priority 그룹별로 처리 — high 먼저
    for level in ("high", "medium", "low"):
        group = [t for t in candidates if t.priority == level]
        # 카테고리별로 잘 분산되도록 round-robin
        by_cat: dict[str, list[BacklogTopic]] = defaultdict(list)
        for t in group:
            by_cat[t.category].append(t)
        while len(picked) < n:
            picked_in_round = False
            for cat in sorted(by_cat.keys(), key=lambda c: category_count[c]):
                if len(picked) >= n:
                    break
                if not by_cat[cat]:
                    continue
                t = by_cat[cat].pop(0)
                sh = simhash64(t.topic)
                if is_recent_duplicate(sh, days=60):
                    log.info("backlog.skip_dup_published", id=t.id, topic=t.topic)
                    continue
                if any(hamming(sh, h) <= in_cycle_gap for h in cycle_simhashes):
                    log.info("backlog.skip_in_cycle_dup", id=t.id, topic=t.topic)
                    continue
                picked.append(t)
                category_count[t.category] += 1
                picked_in_round = True
            if not picked_in_round:
                break
        if len(picked) >= n:
            break

    log.info("backlog.picked", blog=blog_id, n=len(picked),
             categories=dict(category_count))
    return picked
