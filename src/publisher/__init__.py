"""publisher 모듈 — ArticleDraft 를 받아 J-Blog 에 발행."""

from __future__ import annotations

from pathlib import Path

from src.config_loader import get_settings
from src.logging_setup import get_logger
from src.publisher.asset_copier import copy_image
from src.publisher.git_push import publish_files
from src.publisher.jekyll_writer import build_post_filename, build_slug, render_post
from src.publisher.models import ArticleDraft, ImageRef, PublishedInfo, SourceRef
from src.utils.timeutil import now_seoul, today_slug_date

log = get_logger("publisher")


def _stage_images(
    jblog_root: Path,
    images: list[ImageRef],
    slug: str,
) -> tuple[str | None, dict[str, tuple[ImageRef, str]], list[Path]]:
    """이미지들을 J-Blog/assets/ 로 복사하고 (헤더 경로, 본문 마커→경로, stage 대상 리스트) 반환."""
    header_rel: str | None = None
    body_map: dict[str, tuple[ImageRef, str]] = {}
    staged: list[Path] = []

    index = 0
    for img in images:
        relpath = copy_image(jblog_root, img.local_path, slug, index=index)
        staged.append(jblog_root / relpath)
        index += 1
        if img.marker_keyword is None and header_rel is None:
            header_rel = relpath
        elif img.marker_keyword is not None:
            body_map[img.marker_keyword.lower()] = (img, relpath)

    return header_rel, body_map, staged


def publish(draft: ArticleDraft, *, do_push: bool | None = None) -> PublishedInfo:
    """글 1편을 J-Blog 에 작성하고 자동 commit/push.

    do_push=None 이면 settings.dry_run 의 반대값을 사용 (dry_run=true → push 안 함).
    """
    settings = get_settings()
    jblog = settings.jblog_abs_path()
    if do_push is None:
        do_push = not settings.dry_run

    slug = build_slug(draft.title, draft.body_markdown, when=now_seoul().isoformat())

    header_relpath, body_marker_paths, staged_images = _stage_images(jblog, draft.images, slug)

    # 글 파일 작성
    post_fname = build_post_filename(slug, today_slug_date())
    posts_dir = jblog / "_posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    post_path = posts_dir / post_fname
    post_path.write_text(
        render_post(
            draft,
            slug,
            header_relpath=header_relpath,
            body_marker_paths=body_marker_paths,
        ),
        encoding="utf-8",
    )

    log.info(
        "publisher.wrote_post",
        path=str(post_path),
        category=draft.category,
        images=len(staged_images),
    )

    files_to_stage = [post_path, *staged_images]
    commit_msg = f"post: {draft.title}"
    sha, pushed = publish_files(jblog, files_to_stage, commit_msg, do_push=do_push)

    return PublishedInfo(post_path=post_path, slug=slug, commit_sha=sha, pushed=pushed)


__all__ = ["publish", "ArticleDraft", "SourceRef", "ImageRef", "PublishedInfo"]
