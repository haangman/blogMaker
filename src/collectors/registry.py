"""sources.yaml 의 활성 소스를 Collector 인스턴스로 만들어 돌려준다."""

from __future__ import annotations

import importlib
import os

from src.collectors.base import Collector
from src.config_loader import load_sources
from src.logging_setup import get_logger
from src.state.db import connect

log = get_logger("collector.registry")

# 모듈 이름 → 클래스 이름 매핑
_MODULE_CLASS = {
    "hackernews": "HackerNewsCollector",
    "reddit": "RedditCollector",
    "google_news_rss": "GoogleNewsCollector",
    "bbc": "BBCCollector",
    "lobsters": "LobstersCollector",
    "korean_news": "KoreanNewsCollector",
}


def _disabled_source_ids() -> set[str]:
    out: set[str] = set()
    # 환경변수로 즉석 비활성 — 콤마 구분 ID 목록
    env = os.environ.get("BLOGMAKER_DISABLED_SOURCES", "")
    if env:
        out.update(s.strip() for s in env.split(",") if s.strip())
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT source_id FROM source_health WHERE disabled = 1"
            ).fetchall()
        out.update(r["source_id"] for r in rows)
    except Exception:
        pass
    return out


def load_active_collectors() -> list[Collector]:
    out: list[Collector] = []
    disabled = _disabled_source_ids()
    for src in load_sources().get("sources", []):
        if not src.get("enabled"):
            continue
        if src["id"] in disabled:
            log.info("collector.disabled_by_health", source=src["id"])
            continue
        module = src["module"]
        cls_name = _MODULE_CLASS.get(module)
        if not cls_name:
            log.warning("collector.unknown_module", module=module, source=src["id"])
            continue
        try:
            mod = importlib.import_module(f"src.collectors.{module}")
            cls = getattr(mod, cls_name)
        except (ImportError, AttributeError) as e:
            log.warning("collector.import_failed", module=module, error=str(e))
            continue
        out.append(cls(source_id=src["id"], params=src.get("params") or {}))
    return out
