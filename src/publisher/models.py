"""publisher 입출력 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SourceRef:
    url: str
    title: str | None = None


@dataclass
class ImageRef:
    """1편의 글에 첨부되는 이미지 한 장.

    marker_keyword=None  → 헤더 이미지 (본문 상단에 자동 삽입)
    marker_keyword='...' → 본문 내 `[IMAGE: "..."]` 마커 자리로 치환
    """

    local_path: Path
    alt: str
    credit: str = ""
    credit_url: str = ""
    marker_keyword: str | None = None


@dataclass
class ArticleDraft:
    title: str
    body_markdown: str
    category: str               # categories.yaml 의 id (예: 'tech')
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)
    cluster_simhash: int | None = None
    updates_url: str | None = None


@dataclass
class PublishedInfo:
    post_path: Path        # J-Blog 안의 절대경로
    slug: str
    commit_sha: str | None
    pushed: bool
