"""blogmaker CLI 엔트리포인트.

서브커맨드 (점진 추가):
  health       — Claude CLI 인증/연결 헬스체크, .env 검증
  init         — DB 마이그레이션 + 디렉토리 생성
  dry-run      — Step 2 publisher가 추가됨에 따라 가짜 글 1편 발행
  run          — 메인 사이클 (Step 4 이후)
  analyze-persona — Step 6
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from src.config_loader import REPO_ROOT, get_settings
from src.logging_setup import get_logger, setup_logging
from src.state.db import DB_PATH, migrate

app = typer.Typer(add_completion=False, help="blogMaker — 트렌드 기반 자동 블로그")


@app.command()
def health() -> None:
    """Claude CLI 설치/세션과 환경변수가 정상인지 확인."""
    setup_logging()
    log = get_logger("cli.health")
    settings = get_settings()

    # 1) .env 핵심 항목
    log.info("settings.loaded",
             jblog_path=str(settings.jblog_abs_path()),
             dry_run=settings.dry_run,
             max_daily_articles=settings.max_daily_articles,
             claude_cli=settings.claude_cli_path)

    # 2) J-Blog 디렉토리 존재 + 리포 sanity
    jblog = settings.jblog_abs_path()
    if not jblog.exists():
        typer.secho(f"[FAIL] JBLOG_PATH 가 존재하지 않음: {jblog}", fg="red")
        raise typer.Exit(code=1)
    if not (jblog / ".git").exists():
        typer.secho(f"[FAIL] {jblog} 는 git 리포가 아님", fg="red")
        raise typer.Exit(code=1)

    # 3) Claude CLI는 Step 4에서 본격 도입. 일단 PATH 확인만.
    import shutil

    cli_resolved = shutil.which(settings.claude_cli_path) or settings.claude_cli_path
    cli_path = Path(cli_resolved)
    if not cli_path.exists() and shutil.which(settings.claude_cli_path) is None:
        typer.secho(
            f"[WARN] Claude CLI('{settings.claude_cli_path}') 를 PATH 에서 찾지 못함. "
            "Step 4 전까지는 무시 가능하지만 곧 필요해진다.",
            fg="yellow",
        )
    else:
        typer.secho(f"[OK]  Claude CLI: {cli_resolved}", fg="green")

    typer.secho("[OK]  .env 로드 성공", fg="green")
    typer.secho(f"[OK]  J-Blog 리포: {jblog}", fg="green")


@app.command()
def init() -> None:
    """DB 마이그레이션 + 데이터 디렉토리 보장."""
    setup_logging()
    log = get_logger("cli.init")
    migrate()
    log.info("db.migrated", path=str(DB_PATH))
    typer.secho(f"[OK]  DB 마이그레이션 완료: {DB_PATH}", fg="green")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
