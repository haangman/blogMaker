"""arXiv API collector — cs.AI/cs.LG/cs.CL 등 최신 논문."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

import feedparser

from src.collectors.base import Collector, RawItem
from src.logging_setup import get_logger

log = get_logger("collector.arxiv")

BASE_URL = "http://export.arxiv.org/api/query"


def _to_dt(parsed_struct) -> datetime | None:
    if not parsed_struct:
        return None
    try:
        return datetime(*parsed_struct[:6], tzinfo=timezone.utc)
    except Exception:
        return None


class ArxivCollector(Collector):
    def fetch(self) -> list[RawItem]:
        cats = self.params.get("categories", ["cs.AI"])
        limit = int(self.params.get("limit", 50))

        search_query = "+OR+".join(f"cat:{c}" for c in cats)
        query = urlencode(
            {
                "search_query": search_query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "start": 0,
                "max_results": limit,
            }
        )
        url = f"{BASE_URL}?{query}"

        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            log.warning("arxiv.parse_failed", error=str(e))
            return []

        items: list[RawItem] = []
        for entry in parsed.entries[:limit]:
            title = (entry.get("title") or "").strip().replace("\n", " ")
            link = entry.get("link") or entry.get("id") or ""
            summary = (entry.get("summary") or "").strip().replace("\n", " ")
            if not title or not link:
                continue
            arxiv_id = (entry.get("id") or "").split("/")[-1]
            published = _to_dt(entry.get("published_parsed") or entry.get("updated_parsed"))
            authors = [a.get("name", "") for a in (entry.get("authors") or [])]
            primary_cat = ""
            if "tags" in entry and entry["tags"]:
                primary_cat = entry["tags"][0].get("term", "")

            items.append(
                RawItem(
                    source_id=self.source_id,
                    external_id=arxiv_id or link,
                    url=link,
                    title=title,
                    summary=summary[:1200],
                    body="",
                    published_at=published,
                    extra={"authors": authors[:5], "arxiv_category": primary_cat},
                )
            )
        log.info("arxiv.fetched", n=len(items), categories=cats)
        return items
