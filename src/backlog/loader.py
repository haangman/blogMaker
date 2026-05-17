"""백로그 SQLite 액세스 + yaml ↔ DB 양방향 변환."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import yaml

from src.cluster.simhash import simhash64, to_signed64
from src.config_loader import CONFIG_DIR
from src.logging_setup import get_logger
from src.state.db import connect
from src.utils.timeutil import iso_now

log = get_logger("backlog")


@dataclass
class BacklogTopic:
    id: int
    blog_id: str
    topic: str
    category: str
    priority: str          # high|medium|low
    depth: str             # intro|intermediate|deep
    topic_simhash: int     # signed 64
    status: str            # pending|published|skipped
    post_path: str | None
    created_at: str
    published_at: str | None


def _row_to_topic(row: sqlite3.Row) -> BacklogTopic:
    return BacklogTopic(
        id=row["id"],
        blog_id=row["blog_id"],
        topic=row["topic"],
        category=row["category"] or "",
        priority=row["priority"],
        depth=row["depth"],
        topic_simhash=row["topic_simhash"] or 0,
        status=row["status"],
        post_path=row["post_path"],
        created_at=row["created_at"],
        published_at=row["published_at"],
    )


def insert_topics(blog_id: str, topics: list[dict]) -> int:
    """topics: [{topic, category, priority, depth}]. 같은 simhash 가 이미 있으면 skip."""
    if not topics:
        return 0
    inserted = 0
    with connect() as conn:
        # 기존 simhash 인덱스
        existing = {
            int(r["topic_simhash"])
            for r in conn.execute(
                "SELECT topic_simhash FROM backlog WHERE blog_id = ? AND topic_simhash IS NOT NULL",
                (blog_id,),
            ).fetchall()
        }
        for t in topics:
            topic = t.get("topic", "").strip()
            if not topic:
                continue
            sh = to_signed64(simhash64(topic))
            if sh in existing:
                continue
            existing.add(sh)
            conn.execute(
                """
                INSERT INTO backlog
                (blog_id, topic, category, priority, depth, topic_simhash, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    blog_id,
                    topic,
                    t.get("category", "other"),
                    t.get("priority", "medium"),
                    t.get("depth", "intro"),
                    sh,
                    iso_now(),
                ),
            )
            inserted += 1
    log.info("backlog.inserted", blog=blog_id, n=inserted, total_input=len(topics))
    return inserted


def list_pending(blog_id: str, limit: int = 100) -> list[BacklogTopic]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM backlog
            WHERE blog_id = ? AND status = 'pending'
            ORDER BY
              CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
              created_at ASC
            LIMIT ?
            """,
            (blog_id, limit),
        ).fetchall()
    return [_row_to_topic(r) for r in rows]


def mark_published(topic_id: int, post_path: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE backlog SET status = 'published', post_path = ?, published_at = ? WHERE id = ?",
            (post_path, iso_now(), topic_id),
        )


def count_status(blog_id: str) -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM backlog WHERE blog_id = ? GROUP BY status",
            (blog_id,),
        ).fetchall()
    return {r["status"]: r["n"] for r in rows}


def seed_topics_for_blog(blog_id: str, topics: list[dict]) -> int:
    """yaml 시드 등에서 호출. 중복 simhash 는 자동 skip."""
    return insert_topics(blog_id, topics)


def export_to_yaml(blog_id: str, yaml_filename: str) -> None:
    """현재 백로그 상태를 yaml 파일로 export (사람 검수용)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM backlog WHERE blog_id = ? ORDER BY id ASC",
            (blog_id,),
        ).fetchall()
    payload: dict[str, Any] = {
        "blog_id": blog_id,
        "topics": [
            {
                "id": r["id"],
                "topic": r["topic"],
                "category": r["category"],
                "priority": r["priority"],
                "depth": r["depth"],
                "status": r["status"],
                "post_path": r["post_path"],
            }
            for r in rows
        ],
    }
    out_path = CONFIG_DIR / yaml_filename
    out_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    log.info("backlog.exported", blog=blog_id, path=str(out_path), n=len(rows))
