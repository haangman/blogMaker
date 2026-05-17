"""Lobste.rs — HN 보완."""

from __future__ import annotations

from src.collectors._rss_common import RSSCollector


class LobstersCollector(RSSCollector):
    feed_urls = ["https://lobste.rs/rss"]
