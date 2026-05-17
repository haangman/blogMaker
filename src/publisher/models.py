"""publisher 입출력 데이터 모델. 글 본문 + 메타 + 출처."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SourceRef:
    url: str
    title: str | None = None


@dataclass
class ArticleDraft:
    title: str
    body_markdown: str
    category: str               # categories.yaml 의 id (예: 'tech')
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    image_local_path: Path | None = None   # 로컬에 받아둔 이미지. publisher가 J-Blog 로 복사.
    image_alt: str = ""
    image_credit: str = ""                 # "Photo by X on Unsplash" 같은 출처
    cluster_simhash: int | None = None     # Step 5에서 채워진다. None 이면 글 해시로 폴백.


@dataclass
class PublishedInfo:
    post_path: Path        # J-Blog 안의 절대경로
    slug: str
    commit_sha: str | None
    pushed: bool
