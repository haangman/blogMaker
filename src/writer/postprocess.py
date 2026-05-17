"""writer 결과를 발행 가능한 형태로 정리."""

from __future__ import annotations

import re

_LEADING_H1 = re.compile(r"^\s*#\s+.*\n+", re.MULTILINE)
_FRONTMATTER = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

# 모델이 본문 앞에 종종 박는 메타 라벨/머리말 — 본문 첫 라인만 검사해서 제거
_META_LABEL_PATTERNS = [
    re.compile(r"^\s*본문\s*(?:작성합니다|시작|입니다|:)?\s*\.?\s*$"),
    re.compile(r"^\s*(?:여기\s*작성|아래는|다음과\s*같이\s*작성합니다)\s*[\.:]?\s*$"),
    re.compile(r"^\s*글\s*(?:시작|작성)\s*[\.:]?\s*$"),
]


def _strip_meta_label(body: str) -> str:
    """본문 시작부의 메타 라벨 라인을 한 줄 제거 (있으면)."""
    lines = body.split("\n", 1)
    if not lines:
        return body
    first = lines[0]
    for pat in _META_LABEL_PATTERNS:
        if pat.match(first):
            return lines[1] if len(lines) > 1 else ""
    return body


def clean(body: str) -> str:
    body = _FRONTMATTER.sub("", body, count=1)
    body = _LEADING_H1.sub("", body, count=1)
    body = body.strip()
    body = _strip_meta_label(body).lstrip("\n")
    return body
