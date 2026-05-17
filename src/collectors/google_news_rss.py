"""Google News RSS. hl/gl 만 다르면 다국어 신호."""

from __future__ import annotations

from src.collectors._rss_common import RSSCollector


class GoogleNewsCollector(RSSCollector):
    def feeds(self) -> list[str]:
        hl = self.params.get("hl", "ko")
        gl = self.params.get("gl", "KR")
        ceid = self.params.get("ceid", f"{gl}:{hl}")
        topic = self.params.get("topic")  # e.g. "TECHNOLOGY", "BUSINESS"
        if topic:
            return [f"https://news.google.com/rss/headlines/section/topic/{topic}?hl={hl}&gl={gl}&ceid={ceid}"]
        return [f"https://news.google.com/rss?hl={hl}&gl={gl}&ceid={ceid}"]
