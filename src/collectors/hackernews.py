"""HackerNews top stories — 인증 불필요, 1순위 소스."""

from __future__ import annotations

from datetime import datetime, timezone

from src.collectors.base import Collector, RawItem
from src.logging_setup import get_logger
from src.utils.http import make_client

log = get_logger("collector.hn")

TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"


class HackerNewsCollector(Collector):
    def fetch(self) -> list[RawItem]:
        top_n = int(self.params.get("top_n", 30))
        items: list[RawItem] = []
        with make_client(user_agent="blogmaker/0.1 (+https://github.com/haangman/blogMaker)") as client:
            ids = client.get(TOP_URL).json()[:top_n]
            for hn_id in ids:
                try:
                    data = client.get(ITEM_URL.format(id=hn_id)).json()
                except Exception:
                    log.warning("hn.item_fetch_failed", id=hn_id)
                    continue
                if not data or data.get("type") != "story":
                    continue
                url = data.get("url") or f"https://news.ycombinator.com/item?id={hn_id}"
                title = data.get("title", "").strip()
                if not title:
                    continue
                ts = data.get("time")
                published = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
                items.append(
                    RawItem(
                        source_id=self.source_id,
                        external_id=str(hn_id),
                        url=url,
                        title=title,
                        summary="",
                        body="",
                        published_at=published,
                        extra={"score": data.get("score"), "descendants": data.get("descendants")},
                    )
                )
        log.info("hn.fetched", count=len(items))
        return items
