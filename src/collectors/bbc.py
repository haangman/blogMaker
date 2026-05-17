"""BBC News RSS — 안정성 ↑."""

from __future__ import annotations

from src.collectors._rss_common import RSSCollector


class BBCCollector(RSSCollector):
    feed_urls = [
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "http://feeds.bbci.co.uk/news/technology/rss.xml",
    ]
