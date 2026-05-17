"""writer 가 본문에 삽입한 `[IMAGE: "..."]` 마커 파싱 + 검색·다운로드.

마커 형식 (writer 시스템 프롬프트와 정확히 일치):
    [IMAGE: "english search query"]

특징:
- 한 줄에 단독으로 있는 경우를 우선. 문장 안 inline 도 허용.
- 검색어는 영문 권장이지만 한국어도 받음 (Unsplash 가 한·영 모두 처리).
- 매칭 안 된 마커는 publisher 가 본문에서 제거 (graceful).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.images import pexels, unsplash
from src.logging_setup import get_logger
from src.publisher.models import ImageRef

log = get_logger("images.markers")

# `[IMAGE: "..."]` — 따옴표 안의 검색어 추출
MARKER_RE = re.compile(r'\[IMAGE:\s*"([^"]+)"\s*\]')


@dataclass
class ImageMarker:
    keyword: str
    match_start: int
    match_end: int


def extract_markers(body: str) -> list[ImageMarker]:
    out: list[ImageMarker] = []
    for m in MARKER_RE.finditer(body):
        out.append(
            ImageMarker(
                keyword=m.group(1).strip(),
                match_start=m.start(),
                match_end=m.end(),
            )
        )
    return out


def remove_marker_lines(body: str) -> str:
    """매칭되지 못한 마커를 본문에서 조용히 제거.

    한 줄 단독으로 있는 마커는 빈 줄까지 함께 제거 (공백 라인 누적 방지).
    """
    # 한 줄 단독 마커 + 뒤 빈줄까지 통째로
    cleaned = re.sub(
        r'^[ \t]*' + MARKER_RE.pattern + r'[ \t]*\r?\n+',
        "",
        body,
        flags=re.MULTILINE,
    )
    # 그 외 inline 마커는 그냥 제거
    cleaned = MARKER_RE.sub("", cleaned)
    return cleaned


def fetch_for_markers(markers: list[ImageMarker], *, limit: int = 3) -> list[ImageRef]:
    """마커별로 Unsplash → Pexels 순으로 시도. 결과 ImageRef 리스트.

    한 글의 본문 이미지 수는 limit 으로 상한 (시각적 산만함 방지).
    """
    results: list[ImageRef] = []
    seen_keywords: set[str] = set()

    for marker in markers[:limit]:
        kw = marker.keyword.strip()
        if kw.lower() in seen_keywords:
            log.info("marker.duplicate_keyword_skipped", keyword=kw)
            continue
        seen_keywords.add(kw.lower())

        result = unsplash.search_and_download(kw) or pexels.search_and_download(kw)
        if not result:
            log.info("marker.image_not_found", keyword=kw)
            continue

        local_path, meta = result
        credit = meta.get("credit") or ""
        credit_url = meta.get("credit_url") or ""
        results.append(
            ImageRef(
                local_path=local_path,
                alt=meta.get("alt") or kw,
                credit=credit,
                credit_url=credit_url,
                marker_keyword=kw,
            )
        )

    return results
