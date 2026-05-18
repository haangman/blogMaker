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


_MERMAID_BLOCK_RE = re.compile(r"^```mermaid\b", flags=re.MULTILINE)


def _body_has_mermaid(body: str) -> bool:
    return bool(_MERMAID_BLOCK_RE.search(body or ""))


def build_frontmatter(
    draft: ArticleDraft,
    slug: str,
    *,
    categories_file: str = "categories.yaml",
    site_url: str = "",
    baseurl: str = "",
    header_relpath: str | None = None,
    theme: str = "minima",
    body_has_mermaid: bool = False,
) -> dict:
    """블로그 테마별 frontmatter 출력.

    - minima:           기존 형식 (`category: single`, `image: url`)
    - chirpy:           `categories: [c]`, `image: {path, alt}`
    - beautiful-jekyll: `categories: [c]`, `cover-img`, `thumbnail-img`, `subtitle`
    """
    image_abs: str | None = None
    if header_relpath and site_url:
        image_abs = f"{site_url.rstrip('/')}{baseurl}/{header_relpath.lstrip('/')}"
    cat_ko = _category_label_ko(draft.category, categories_file)

    # minimal-mistakes 는 layout: single 이 표준 글 레이아웃. 다른 테마는 layout: post.
    layout = "single" if theme == "minimal-mistakes" else "post"

    meta: dict = {
        "layout": layout,
        "title": draft.title,
        "date": iso_now(),
        "tags": draft.tags,
        "summary": draft.summary,
        "description": draft.summary,
        "slug": slug,
    }

    if theme == "chirpy":
        meta["categories"] = [draft.category]
        meta["category_ko"] = cat_ko
        if image_abs:
            meta["image"] = {"path": image_abs, "alt": draft.title}
        # chirpy 는 글에 mermaid 블록이 있을 때 frontmatter mermaid: true 필요.
        if body_has_mermaid:
            meta["mermaid"] = True
    elif theme == "beautiful-jekyll":
        meta["categories"] = [draft.category]
        meta["category_ko"] = cat_ko
        if draft.summary:
            meta["subtitle"] = draft.summary[:120]
        if image_abs:
            meta["cover-img"] = image_abs
            meta["thumbnail-img"] = image_abs
            meta["share-img"] = image_abs
            meta["image"] = image_abs   # jekyll-seo-tag 도 인식
    elif theme == "minimal-mistakes":
        # minimal-mistakes: header.teaser + header.overlay_image 가 핵심 비주얼.
        # excerpt 가 archive 페이지 카드 발췌문으로 사용된다.
        meta["categories"] = [draft.category]
        meta["category_ko"] = cat_ko
        if draft.summary:
            meta["excerpt"] = draft.summary[:160]
        if image_abs:
            meta["header"] = {
                "teaser": image_abs,
                "overlay_image": image_abs,
                "overlay_filter": 0.35,   # 어둡게 — 텍스트 가독성
            }
            meta["image"] = image_abs  # jekyll-seo-tag 호환 (og:image)
    else:  # minima 등
        meta["category"] = draft.category
        meta["category_ko"] = cat_ko
        if image_abs:
            meta["image"] = image_abs

    if draft.sources:
        meta["sources"] = [{"url": s.url, "title": s.title} for s in draft.sources]
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
    categories_file: str = "categories.yaml",
    site_url: str = "",
    baseurl: str = "",
    theme: str = "minima",
) -> str:
    """글 1편의 최종 마크다운 (frontmatter + 본문) 반환.

    - header_relpath: 본문 상단에 삽입할 헤더 이미지의 baseurl 기준 상대경로
    - body_marker_paths: 키워드(소문자) → (ImageRef, 상대경로) 매핑
    """
    parts: list[str] = []

    # 1) 헤더 이미지 — minima 만 본문에 마크다운으로 삽입.
    #    chirpy/beautiful-jekyll/minimal-mistakes 는 frontmatter 의 hero/cover/overlay 가
    #    본문 위에 자동 렌더링되므로 본문 마크다운으로 또 넣으면 이미지가 두 번 보인다.
    header = next((im for im in draft.images if im.marker_keyword is None), None)
    if header and header_relpath and theme == "minima":
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
    fm = build_frontmatter(
        draft,
        slug,
        categories_file=categories_file,
        site_url=site_url,
        baseurl=baseurl,
        header_relpath=header_relpath,
        theme=theme,
        body_has_mermaid=_body_has_mermaid(full),
    )
    return build_markdown(fm, full)
