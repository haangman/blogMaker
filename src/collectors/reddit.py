"""Reddit — /r/<sub>/top.json. 인증 없이 User-Agent 만 정중하게."""

from __future__ import annotations

from datetime import datetime, timezone

from src.collectors.base import Collector, RawItem
from src.logging_setup import get_logger
from src.utils.http import make_client

log = get_logger("collector.reddit")


class RedditCollector(Collector):
    def fetch(self) -> list[RawItem]:
        sub = self.params.get("subreddit", "popular")
        limit = int(self.params.get("limit", 50))
        sort = self.params.get("sort", "top")
        period = self.params.get("t", "day")
        url = f"https://www.reddit.com/r/{sub}/{sort}.json"
        try:
            with make_client() as client:
                resp = client.get(url, params={"limit": limit, "t": period})
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            log.warning("reddit.fetch_failed", subreddit=sub, error=str(e))
            return []

        items: list[RawItem] = []
        for child in payload.get("data", {}).get("children", []):
            d = child.get("data") or {}
            if d.get("over_18"):
                continue
            url_ext = d.get("url_overridden_by_dest") or d.get("url") or ""
            title = (d.get("title") or "").strip()
            if not title:
                continue
            if not url_ext or url_ext.startswith("/r/"):
                url_ext = f"https://www.reddit.com{d.get('permalink', '')}"
            created = d.get("created_utc")
            published = (
                datetime.fromtimestamp(created, tz=timezone.utc) if created else None
            )
            items.append(
                RawItem(
                    source_id=self.source_id,
                    external_id=d.get("id") or url_ext,
                    url=url_ext,
                    title=title,
                    summary=(d.get("selftext") or "")[:600],
                    body="",
                    published_at=published,
                    extra={"score": d.get("score"), "subreddit": sub},
                )
            )
        log.info("reddit.fetched", subreddit=sub, n=len(items))
        return items
