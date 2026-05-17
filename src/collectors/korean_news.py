"""한국 매체 RSS 종합 — 연합뉴스, ETNews 등."""

from __future__ import annotations

from src.collectors._rss_common import RSSCollector


class KoreanNewsCollector(RSSCollector):
    feed_urls = [
        # 연합뉴스 — 카테고리별 RSS
        "https://www.yna.co.kr/RSS/news.xml",
        "https://www.yna.co.kr/RSS/economy.xml",
        # ETNews — 일반 RSS
        "https://rss.etnews.com/Section020.xml",
        # 한겨레 — 사회/문화
        "https://www.hani.co.kr/rss/society/",
        "https://www.hani.co.kr/rss/culture/",
    ]
