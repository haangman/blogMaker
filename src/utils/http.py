"""httpx 클라이언트 팩토리 — 표준 UA·타임아웃·재시도 정책."""

from __future__ import annotations

import httpx

from src.config_loader import get_settings

DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=8.0, read=15.0)


def make_client(*, user_agent: str | None = None) -> httpx.Client:
    settings = get_settings()
    ua = user_agent or settings.reddit_user_agent or "blogmaker/0.1"
    return httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        http2=False,  # 일부 사이트는 http/2 협상 불안정 — 안정성 우선
        headers={"User-Agent": ua, "Accept-Language": "ko,en;q=0.8"},
        follow_redirects=True,
    )
