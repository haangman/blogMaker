"""writer 결과를 발행 가능한 형태로 정리."""

from __future__ import annotations

import re

_LEADING_H1 = re.compile(r"^\s*#\s+.*\n+", re.MULTILINE)
_FRONTMATTER = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def clean(body: str) -> str:
    body = _FRONTMATTER.sub("", body, count=1)
    body = _LEADING_H1.sub("", body, count=1)
    body = body.strip()
    return body
