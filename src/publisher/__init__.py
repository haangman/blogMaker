"""publisher 모듈 — ArticleDraft 를 받아 J-Blog 에 발행."""

from __future__ import annotations

from pathlib import Path

from src.config_loader import get_settings
from src.logging_setup import get_logger
from src.publisher.asset_copier import copy_image
from src.publisher.git_push import publish_files
from src.publisher.jekyll_writer import build_post_filename, build_slug, render_post
from src.publisher.models import ArticleDraft, PublishedInfo, SourceRef
from src.utils.timeutil import now_seoul, today_slug_date

log = get_logger("publisher")


def publish(draft: ArticleDraft, *, do_push: bool | None = None) -> PublishedInfo:
    """글 1편을 J-Blog 에 작성하고 자동 commit/push.

    do_push=None 이면 settings.dry_run 의 반대값을 사용 (dry_run=true → push 안 함).
    """
    settings = get_settings()
    jblog = settings.jblog_abs_path()
    if do_push is None:
        do_push = not settings.dry_run

    slug = build_slug(draft.title, draft.body_markdown, when=now_seoul().isoformat())

    image_relpath: str | None = None
    files_to_stage: list[Path] = []

    if draft.image_local_path:
        image_relpath = copy_image(jblog, draft.image_local_path, slug)
        files_to_stage.append(jblog / image_relpath)

    post_fname = build_post_filename(slug, today_slug_date())
    posts_dir = jblog / "_posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    post_path = posts_dir / post_fname
    post_path.write_text(render_post(draft, slug, image_relpath), encoding="utf-8")
    files_to_stage.append(post_path)

    log.info("publisher.wrote_post", path=str(post_path), category=draft.category)

    commit_msg = f"post: {draft.title}"
    sha, pushed = publish_files(jblog, files_to_stage, commit_msg, do_push=do_push)

    return PublishedInfo(post_path=post_path, slug=slug, commit_sha=sha, pushed=pushed)


__all__ = ["publish", "ArticleDraft", "SourceRef", "PublishedInfo"]
