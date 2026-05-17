"""J-Blog 리포 안에 `_posts/YYYY-MM-DD-slug.md` 파일 작성."""

from __future__ import annotations

from pathlib import Path

from slugify import slugify

from src.config_loader import load_categories
from src.publisher.frontmatter import build_markdown
from src.publisher.models import ArticleDraft
from src.utils.hashing import short_hash
from src.utils.timeutil import iso_now, now_seoul, today_slug_date


def _category_label_ko(category_id: str) -> str:
    for cat in load_categories().get("categories", []):
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


def render_post(draft: ArticleDraft, slug: str, image_relpath: str | None) -> str:
    """이미지 경로(J-Blog 기준 상대경로)를 받아 본문 상단에 삽입한 마크다운을 반환."""
    parts: list[str] = []

    if image_relpath:
        alt = draft.image_alt or draft.title
        parts.append(f'![{alt}]({{{{ site.baseurl }}}}/{image_relpath.lstrip("/")})')
        if draft.image_credit:
            parts.append(f"*{draft.image_credit}*")
        parts.append("")

    parts.append(draft.body_markdown.rstrip())

    if draft.sources:
        parts.append("")
        # `---` 대신 `***` — 본문에 들어간 단독 `---` 는 sanitize 가 잡는데
        # 그게 우리가 의도해서 넣은 sources 구분자까지 함께 잡아버리는 사고를 막기 위함.
        parts.append("***")
        parts.append("")
        parts.append("**참고**")
        parts.append("")
        for s in draft.sources:
            label = s.title or s.url
            parts.append(f"- [{label}]({s.url})")

    body = "\n".join(parts)
    return build_markdown(build_frontmatter(draft, slug), body)


def write_post(jblog_root: Path, draft: ArticleDraft, image_relpath: str | None = None) -> Path:
    """글을 디스크에 쓰고 절대경로 반환. 디렉토리 보장."""
    slug = build_slug(draft.title, draft.body_markdown, when=now_seoul().isoformat())
    fname = build_post_filename(slug)
    posts_dir = jblog_root / "_posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    post_path = posts_dir / fname

    content = render_post(draft, slug, image_relpath)
    post_path.write_text(content, encoding="utf-8")
    return post_path
