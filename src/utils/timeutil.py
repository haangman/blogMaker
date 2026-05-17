"""Asia/Seoul 기준 시간 유틸. 슬러그 날짜와 글 발행시각 일관성용."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")


def now_seoul() -> datetime:
    return datetime.now(SEOUL)


def today_slug_date() -> str:
    return now_seoul().strftime("%Y-%m-%d")


def iso_now() -> str:
    return now_seoul().isoformat(timespec="seconds")
