"""sources.yaml 의 활성 소스를 Collector 인스턴스로 만들어 돌려준다."""

from __future__ import annotations

import importlib

from src.collectors.base import Collector
from src.config_loader import load_sources
from src.logging_setup import get_logger

log = get_logger("collector.registry")

# 모듈 이름 → 클래스 이름 매핑
_MODULE_CLASS = {
    "hackernews": "HackerNewsCollector",
    "reddit": "RedditCollector",
    "google_news_rss": "GoogleNewsCollector",
    "bbc": "BBCCollector",
    "lobsters": "LobstersCollector",
}


def load_active_collectors() -> list[Collector]:
    out: list[Collector] = []
    for src in load_sources().get("sources", []):
        if not src.get("enabled"):
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
