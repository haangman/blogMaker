"""Jekyll 프론트매터 빌더 + 마크다운 직렬화.

`python-frontmatter` 를 직접 쓰면 본문에 단독 `---` 라인이 있을 때 깨질 위험이 있어
직렬화 단계에서 본문을 미리 sanitize 한 뒤 라이브러리에 넘긴다.
"""

from __future__ import annotations

import re
from typing import Any

import frontmatter

_BARE_HR = re.compile(r"^---\s*$", flags=re.MULTILINE)


def sanitize_body(body: str) -> str:
    """본문에서 단독 `---` 라인을 `— —` 로 치환해 프론트매터 경계 충돌 방지."""
    return _BARE_HR.sub("— —", body)


def build_markdown(meta: dict[str, Any], body: str) -> str:
    post = frontmatter.Post(content=sanitize_body(body), **meta)
    return frontmatter.dumps(post, sort_keys=False)
