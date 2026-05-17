"""DB 액세스 헬퍼 — published / source_health / article_attempts / llm_calls."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from src.cluster.simhash import to_signed64
from src.utils.timeutil import iso_now, now_seoul


def record_published(
    conn: sqlite3.Connection,
    *,
    cluster_simhash: int,
    title: str,
    category: str,
    post_path: str,
    source_urls: list[str],
    cluster_embedding: bytes | None = None,
    blog_id: str = "trends",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO published
        (cluster_simhash, cluster_embedding, title, category, post_path,
         published_at, source_urls, blog_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            to_signed64(cluster_simhash),
            cluster_embedding,
            title,
            category,
            post_path,
            iso_now(),
            json.dumps(source_urls, ensure_ascii=False),
            blog_id,
        ),
    )
    return cur.lastrowid or 0


def published_recently(
    conn: sqlite3.Connection, *, days: int = 30
) -> list[sqlite3.Row]:
    since = (now_seoul() - timedelta(days=days)).isoformat()
    return conn.execute(
        "SELECT * FROM published WHERE published_at >= ? ORDER BY published_at DESC",
        (since,),
    ).fetchall()


def record_attempt(
    conn: sqlite3.Connection,
    *,
    cluster_simhash: int | None,
    attempt_num: int,
    gate_score: float | None,
    gate_failures: list[str],
    outcome: str,
) -> None:
    conn.execute(
        """
        INSERT INTO article_attempts
        (cluster_simhash, attempt_num, gate_score, gate_failures, outcome, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            to_signed64(cluster_simhash) if cluster_simhash is not None else None,
            attempt_num,
            gate_score,
            json.dumps(gate_failures, ensure_ascii=False),
            outcome,
            iso_now(),
        ),
    )


def record_llm_call(
    conn: sqlite3.Connection,
    *,
    purpose: str,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None,
    cost_usd: float | None,
    duration_ms: int | None,
    success: bool,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO llm_calls
        (purpose, model, input_tokens, output_tokens, cached_tokens,
         cost_usd, duration_ms, success, error, at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            purpose,
            model,
            input_tokens,
            output_tokens,
            cached_tokens,
            cost_usd,
            duration_ms,
            1 if success else 0,
            error,
            iso_now(),
        ),
    )


def record_source_failure(conn: sqlite3.Connection, source_id: str, error: str) -> None:
    conn.execute(
        """
        INSERT INTO source_health (source_id, consec_failures, last_error)
        VALUES (?, 1, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            consec_failures = consec_failures + 1,
            last_error = excluded.last_error,
            disabled = CASE WHEN consec_failures + 1 >= 3 THEN 1 ELSE disabled END
        """,
        (source_id, error),
    )


def record_source_success(conn: sqlite3.Connection, source_id: str) -> None:
    conn.execute(
        """
        INSERT INTO source_health (source_id, consec_failures, last_success_at)
        VALUES (?, 0, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            consec_failures = 0,
            last_success_at = excluded.last_success_at,
            disabled = 0
        """,
        (source_id, iso_now()),
    )
