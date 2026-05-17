"""RSS 기반 collector 공통 로직 — BBC/Google News/Korean/Lobsters 가 공유."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import feedparser

from src.collectors.base import Collector, RawItem
from src.logging_setup import get_logger

log = get_logger("collector.rss")


def _to_dt(parsed_struct) -> datetime | None:
    if not parsed_struct:
        return None
    try:
        return datetime(*parsed_struct[:6], tzinfo=timezone.utc)
    except Exception:
        return None


class RSSCollector(Collector):
    """단일 또는 다중 RSS URL 을 받아 RawItem 리스트로 정규화."""

    feed_urls: list[str] = []

    def __init__(self, source_id: str, params: dict | None = None):
        super().__init__(source_id, params)

    def feeds(self) -> list[str]:
        urls = self.params.get("urls") or self.params.get("url")
        if isinstance(urls, str):
            return [urls]
        if isinstance(urls, list):
            return urls
        return self.feed_urls

    def parse_extra(self, entry: dict) -> dict[str, Any]:
        return {}

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        limit = int(self.params.get("limit", 50))
        for feed_url in self.feeds():
            try:
                parsed = feedparser.parse(feed_url)
            except Exception as e:
                log.warning("rss.parse_failed", url=feed_url, error=str(e))
                continue
            for entry in parsed.entries[:limit]:
                link = entry.get("link") or ""
                title = (entry.get("title") or "").strip()
                if not link or not title:
                    continue
                summary = (entry.get("summary") or "").strip()
                published = _to_dt(entry.get("published_parsed") or entry.get("updated_parsed"))
                ext_id = entry.get("id") or link
                items.append(
                    RawItem(
                        source_id=self.source_id,
                        external_id=str(ext_id),
                        url=link,
                        title=title,
                        summary=summary[:1000],
                        body="",
                        published_at=published,
                        extra=self.parse_extra(entry),
                    )
                )
        log.info("rss.fetched", source=self.source_id, n=len(items))
        return items
