"""SQLite 연결과 스키마 마이그레이션."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from src.config_loader import DATA_DIR

SCHEMA_VERSION = 2  # V4: published.blog_id, article_attempts.blog_id, llm_calls.blog_id, backlog 테이블
DB_PATH = DATA_DIR / "state.sqlite"
SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == column for row in cur.fetchall())


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """기존 row 가 trends 블로그에 속하도록 backfill."""
    if not _column_exists(conn, "published", "blog_id"):
        conn.execute("ALTER TABLE published ADD COLUMN blog_id TEXT NOT NULL DEFAULT 'trends'")
    if not _column_exists(conn, "article_attempts", "blog_id"):
        conn.execute("ALTER TABLE article_attempts ADD COLUMN blog_id TEXT")
    if not _column_exists(conn, "llm_calls", "blog_id"):
        conn.execute("ALTER TABLE llm_calls ADD COLUMN blog_id TEXT")


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(path: Path = DB_PATH) -> None:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with _connect(path) as conn:
        # schema_version 테이블만 먼저 생성해서 현재 버전 읽기
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        current = row["v"] if row and row["v"] is not None else 0

        # V1→V2 ALTER TABLE 을 전체 schema 실행 전에 (인덱스 생성 시점에 컬럼이 있도록)
        if current >= 1 and current < 2:
            _migrate_v1_to_v2(conn)

        # 전체 스키마 실행 (IF NOT EXISTS 라 기존 테이블엔 영향 없음)
        conn.executescript(sql)

        if current < SCHEMA_VERSION:
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()


@contextmanager
def connect(path: Path = DB_PATH):
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
