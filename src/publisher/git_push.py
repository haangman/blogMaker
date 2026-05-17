"""J-Blog 리포 자동 git add/commit/push.

가드: push 전 `git -C <path> rev-parse --show-toplevel` 결과의 디렉토리 이름이
'J-Blog' 인지 확인. 아니면 작업 거부 — blogMaker 자신을 잘못 push 하는 사고 방지.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.config_loader import get_settings
from src.logging_setup import get_logger
from src.utils.retry import standard_retry

log = get_logger("publisher.git")


class RepoSanityError(RuntimeError):
    pass


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args[1:])} 실패 (exit={result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def assert_is_jblog_repo(jblog_root: Path) -> None:
    if not (jblog_root / ".git").exists():
        raise RepoSanityError(f"{jblog_root} 는 git 리포가 아님")
    top = _run(["git", "rev-parse", "--show-toplevel"], cwd=jblog_root)
    top_name = Path(top).name
    if top_name.lower() != "j-blog":
        raise RepoSanityError(
            f"리포 sanity 실패: 예상 'J-Blog', 실제 '{top_name}' (path={top})"
        )


def stage_paths(jblog_root: Path, paths: list[Path]) -> None:
    rels = [str(p.relative_to(jblog_root)) for p in paths]
    if not rels:
        return
    _run(["git", "add", "--", *rels], cwd=jblog_root)


def commit(jblog_root: Path, message: str) -> str:
    settings = get_settings()
    args = ["git"]
    if settings.git_user_name:
        args += ["-c", f"user.name={settings.git_user_name}"]
    if settings.git_user_email:
        args += ["-c", f"user.email={settings.git_user_email}"]
    args += ["commit", "-m", message]
    _run(args, cwd=jblog_root)
    return _run(["git", "rev-parse", "HEAD"], cwd=jblog_root)


@standard_retry()
def push(jblog_root: Path, branch: str = "main") -> None:
    _run(["git", "push", "origin", branch], cwd=jblog_root)


def publish_files(
    jblog_root: Path,
    files: list[Path],
    commit_message: str,
    do_push: bool = True,
) -> tuple[str | None, bool]:
    """리포 sanity → stage → commit → push. (commit_sha, pushed) 반환.

    stage 대상에 변화가 없으면 (None, False) 반환.
    """
    assert_is_jblog_repo(jblog_root)
    stage_paths(jblog_root, files)

    status = _run(["git", "status", "--porcelain"], cwd=jblog_root)
    if not status:
        log.info("publisher.no_changes", repo=str(jblog_root))
        return None, False

    sha = commit(jblog_root, commit_message)
    log.info("publisher.commit", sha=sha, repo=str(jblog_root))

    if not do_push:
        return sha, False

    push(jblog_root)
    log.info("publisher.pushed", sha=sha, repo=str(jblog_root))
    return sha, True
