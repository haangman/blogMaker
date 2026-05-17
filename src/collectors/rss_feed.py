"""범용 RSS feed collector — sources.yaml 에 url 만 적으면 동작.

이미 있는 _rss_common.RSSCollector 를 그대로 노출하되 모듈 이름을 'rss_feed' 로.
"""

from __future__ import annotations

from src.collectors._rss_common import RSSCollector


class GenericRSSCollector(RSSCollector):
    """params: { url: '...', limit: 30 }"""
    pass
