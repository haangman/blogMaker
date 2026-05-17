"""HDBSCAN 으로 NormalizedItem 클러스터링.

데이터가 적을 때(< 10) HDBSCAN 이 모두 노이즈로 잡는 경우가 있어
코사인 임계값(0.78) + union-find 폴백으로 보강.
"""

from __future__ import annotations

import numpy as np

from src.cluster.embed import embed
from src.logging_setup import get_logger
from src.normalize.item import NormalizedItem

log = get_logger("cluster.hdbscan")


def _items_to_text(items: list[NormalizedItem]) -> list[str]:
    return [
        " ".join([it.title or "", (it.body or "")[:300]]).strip()
        for it in items
    ]


def _union_find_cluster(vecs: np.ndarray, threshold: float = 0.78) -> list[int]:
    n = vecs.shape[0]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    sim = vecs @ vecs.T  # 이미 정규화돼 있으므로 cosine
    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= threshold:
                union(i, j)
    roots = {find(i) for i in range(n)}
    label_map = {r: idx for idx, r in enumerate(sorted(roots))}
    return [label_map[find(i)] for i in range(n)]


def cluster_items(items: list[NormalizedItem]) -> list[list[NormalizedItem]]:
    if not items:
        return []
    texts = _items_to_text(items)
    vecs = embed(texts)
    if vecs.shape[0] < 5:
        labels = _union_find_cluster(vecs)
    else:
        try:
            import hdbscan
            labels = list(
                hdbscan.HDBSCAN(min_cluster_size=3, min_samples=2, metric="euclidean")
                .fit_predict(vecs)
            )
        except Exception as e:
            log.warning("cluster.hdbscan_failed_fallback", error=str(e))
            labels = _union_find_cluster(vecs)

    # 노이즈(-1) 는 버려 — 단일 항목 클러스터는 신호 약함
    grouped: dict[int, list[NormalizedItem]] = {}
    for it, lbl in zip(items, labels, strict=True):
        if lbl == -1:
            continue
        grouped.setdefault(int(lbl), []).append(it)

    return list(grouped.values())
