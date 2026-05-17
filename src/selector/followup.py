"""8~30일 이내 이미 발행된 비슷한 사건이 있으면 follow-up 글로 변환."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np

from src.cluster.merge import TopicCluster
from src.logging_setup import get_logger
from src.state.db import connect
from src.utils.timeutil import now_seoul

log = get_logger("selector.followup")

# 임베딩 코사인 임계 (1.0 = 동일, 0.88 = 매우 유사)
FOLLOWUP_COSINE_THRESHOLD = 0.88
FOLLOWUP_WINDOW_MIN_DAYS = 8
FOLLOWUP_WINDOW_MAX_DAYS = 30


@dataclass
class FollowupContext:
    previous_post_path: str
    previous_title: str
    previous_summary: str
    previous_url: str | None     # site.baseurl 기준 상대 또는 절대
    cosine: float


def _decode_embedding(blob: bytes | None) -> np.ndarray | None:
    if not blob:
        return None
    try:
        return np.frombuffer(blob, dtype=np.float32)
    except Exception:
        return None


def encode_embedding(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def _relative_post_url(post_path: str) -> str | None:
    """J-Blog/_posts/YYYY-MM-DD-slug.md → /YYYY/MM/DD/slug/ (Jekyll permalink)."""
    p = Path(post_path)
    name = p.stem  # YYYY-MM-DD-slug
    parts = name.split("-", 3)
    if len(parts) < 4:
        return None
    yyyy, mm, dd, slug = parts
    return f"/{yyyy}/{mm}/{dd}/{slug}/"


def find_followup(cluster: TopicCluster) -> FollowupContext | None:
    if cluster.embedding is None:
        return None

    since = (now_seoul() - timedelta(days=FOLLOWUP_WINDOW_MAX_DAYS)).isoformat()
    until = (now_seoul() - timedelta(days=FOLLOWUP_WINDOW_MIN_DAYS)).isoformat()

    rows: list[sqlite3.Row]
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM published
            WHERE published_at >= ? AND published_at <= ?
              AND cluster_embedding IS NOT NULL
            ORDER BY published_at DESC
            """,
            (since, until),
        ).fetchall()

    q = cluster.embedding / (np.linalg.norm(cluster.embedding) + 1e-9)
    best: FollowupContext | None = None
    best_sim = 0.0

    for r in rows:
        v = _decode_embedding(r["cluster_embedding"])
        if v is None or v.size != q.size:
            continue
        v = v / (np.linalg.norm(v) + 1e-9)
        sim = float(np.dot(q, v))
        if sim >= FOLLOWUP_COSINE_THRESHOLD and sim > best_sim:
            best_sim = sim
            best = FollowupContext(
                previous_post_path=r["post_path"],
                previous_title=r["title"],
                previous_summary="",
                previous_url=_relative_post_url(r["post_path"]),
                cosine=sim,
            )

    if best:
        log.info("followup.match", cosine=best.cosine, prev=best.previous_title)
    return best
