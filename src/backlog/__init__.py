"""백로그 — '꼭 정리해야 할' 토픽 목록. AI 블로그에서 트렌드와 함께 발행.

LLM 자동 시드(seed_backlog) → SQLite 저장 → 사이클이 pending 항목을 점수+카테고리
분산으로 골라 발행. 발행 후 status=published.

기존 yaml 파일 형태도 있지만(`config/ai_backlog.yaml`) 1차 진실원은 SQLite.
yaml 은 사람 검수/수동 추가용 export/import 보조 도구.
"""

from src.backlog.loader import (
    BacklogTopic,
    insert_topics,
    list_pending,
    mark_published,
    seed_topics_for_blog,
)
from src.backlog.seed import seed_backlog
from src.backlog.selector import pick_backlog_topics

__all__ = [
    "BacklogTopic",
    "insert_topics",
    "list_pending",
    "mark_published",
    "seed_topics_for_blog",
    "seed_backlog",
    "pick_backlog_topics",
]
