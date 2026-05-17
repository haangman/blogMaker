"""J-Blog 리포 안에 `_posts/YYYY-MM-DD-slug.md` 파일 작성.

본문에는 writer 가 삽입한 `[IMAGE: "..."]` 마커가 들어있고,
이 모듈이 마커를 실제 마크다운 이미지 + 크레딧으로 치환한다.
매칭 안 된 마커는 조용히 제거.
"""

from __future__ import annotations

import re
from pathlib import Path

from slugify import slugify

from src.config_loader import load_categories, load_yaml
from src.publisher.frontmatter import build_markdown
from src.publisher.models import ArticleDraft, ImageRef
from src.utils.hashing import short_hash
from src.utils.timeutil import iso_now, now_seoul, today_slug_date

# `[IMAGE: "..."]` 마커 — src.images.markers 와 동일 패턴 (순환 import 회피용 사본)
_MARKER_RE = re.compile(r'\[IMAGE:\s*"([^"]+)"\s*\]')
_LONE_MARKER_LINE_RE = re.compile(
    r'^[ \t]*' + _MARKER_RE.pattern + r'[ \t]*\r?\n+',
    flags=re.MULTILINE,
)


def _strip_unmatched_markers(body: str) -> str:
    """매칭되지 않은 마커를 본문에서 조용히 제거."""
    body = _LONE_MARKER_LINE_RE.sub("", body)
    body = _MARKER_RE.sub("", body)
    return body


def _category_label_ko(category_id: str, categories_file: str = "categories.yaml") -> str:
    if categories_file == "categories.yaml":
        cats = load_categories().get("categories", [])
    else:
        cats = load_yaml(categories_file).get("categories", [])
    for cat in cats:
        if cat.get("id") == category_id:
            return cat.get("label_ko", category_id)
    return category_id


def build_slug(title: str, body: str, when: str | None = None) -> str:
    base = slugify(title, allow_unicode=True, max_length=60) or "post"
    suffix = short_hash((when or "") + title + body, length=6)
    return f"{base}-{suffix}"


def build_post_filename(slug: str, date_str: str | None = None) -> str:
    return f"{date_str or today_slug_date()}-{slug}.md"


def build_frontmatter(draft: ArticleDraft, slug: str) -> dict:
    meta: dict = {
        "layout": "post",
        "title": draft.title,
        "date": iso_now(),
        "category": draft.category,
        "category_ko": _category_label_ko(draft.category),
        "tags": draft.tags,
        "summary": draft.summary,
        "slug": slug,
        "sources": [{"url": s.url, "title": s.title} for s in draft.sources],
    }
    if draft.updates_url:
        meta["updates"] = draft.updates_url
    return meta


def _image_markdown(image: ImageRef, relpath: str) -> str:
    alt = image.alt or "image"
    lines = [f'![{alt}]({{{{ site.baseurl }}}}/{relpath.lstrip("/")})']
    if image.credit:
        if image.credit_url:
            lines.append(f"*[{image.credit}]({image.credit_url})*")
        else:
            lines.append(f"*{image.credit}*")
    return "\n".join(lines)


def _replace_body_markers(body: str, marker_to_relpath: dict[str, tuple[ImageRef, str]]) -> str:
    """본문 마커를 ImageRef + 상대경로로 치환. 매칭 안 된 마커는 제거."""

    def repl(m):
        kw = m.group(1).strip().lower()
        pair = marker_to_relpath.get(kw)
        if not pair:
            return ""  # 매칭 안 됨 — 조용히 제거
        image, relpath = pair
        return "\n\n" + _image_markdown(image, relpath) + "\n\n"

    replaced = _MARKER_RE.sub(repl, body)
    return _strip_unmatched_markers(replaced)


def render_post(
    draft: ArticleDraft,
    slug: str,
    *,
    header_relpath: str | None = None,
    body_marker_paths: dict[str, tuple[ImageRef, str]] | None = None,
) -> str:
    """글 1편의 최종 마크다운 (frontmatter + 본문) 반환.

    - header_relpath: 본문 상단에 삽입할 헤더 이미지의 baseurl 기준 상대경로
    - body_marker_paths: 키워드(소문자) → (ImageRef, 상대경로) 매핑
    """
    parts: list[str] = []

    # 1) 헤더 이미지
    header = next((im for im in draft.images if im.marker_keyword is None), None)
    if header and header_relpath:
        parts.append(_image_markdown(header, header_relpath))
        parts.append("")

    # 2) 본문 — 마커 치환 후
    body = draft.body_markdown.rstrip()
    if body_marker_paths:
        body = _replace_body_markers(body, body_marker_paths)
    else:
        # 헤더만 있고 본문 마커 처리가 없는 경우라도 잔여 마커는 제거
        body = _strip_unmatched_markers(body)
    parts.append(body)

    # 3) sources 섹션
    if draft.sources:
        parts.append("")
        parts.append("***")
        parts.append("")
        parts.append("**참고**")
        parts.append("")
        for s in draft.sources:
            label = s.title or s.url
            parts.append(f"- [{label}]({s.url})")

    full = "\n".join(parts)
    return build_markdown(build_frontmatter(draft, slug), full)
