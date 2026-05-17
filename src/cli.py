"""blogmaker CLI 엔트리포인트.

서브커맨드 (점진 추가):
  health       — Claude CLI 인증/연결 헬스체크, .env 검증
  init         — DB 마이그레이션 + 디렉토리 생성
  dry-run      — placeholder 글 1편을 J-Blog 에 자동 발행 (Step 2)
  run          — 메인 사이클 (Step 4 이후)
  analyze-persona — Step 6
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from src.config_loader import REPO_ROOT, get_settings
from src.logging_setup import get_logger, setup_logging
from src.publisher import ArticleDraft, SourceRef, publish
from src.state.db import DB_PATH, migrate

app = typer.Typer(add_completion=False, help="blogMaker — 트렌드 기반 자동 블로그")


from collections import defaultdict
from urllib.parse import urlparse

from src.persona import analyze as persona_analyze
from src.persona import fetch_articles, fetch_bodies, save_generated, save_samples


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


_PLACEHOLDER_BODY = """\
처음으로 글을 자동으로 올려본다. 아직 본문은 사람이 쓴 흉내만 낸 것이고,
글을 진짜로 만들어주는 부분은 다음 단계에서 붙는다.

사실은 이 글의 목적은 글이 잘 읽히는지가 아니라, **글이 잘 올라가는지** 다.
파일이 J-Blog 리포의 `_posts/` 에 정확한 형식으로 들어가고, 자동 commit 후
push 까지 한 번에 흘러가서, 1~2분 뒤 GitHub Pages 에 노출되는지를 본다.

근데 한 가지는 짚어두고 싶다. 이 자리에는 곧 진짜 글이 들어온다. 그땐
"오늘은 ~에 대해 알아보겠습니다" 같은 정형 문구 없이, 어디서 본 토픽이
사실은 다른 어떤 흐름과 이어져 있는지에 대한 짧은 관찰이 자리할 거다.

이 글은 발행 파이프라인이 잘 돌아가는지 확인하고 나면 지워도 된다.
"""


@app.command("dry-run")
def dry_run(
    title: str = typer.Option(
        "scaffold 검증용 더미 글",
        "--title",
        "-t",
        help="발행할 글 제목.",
    ),
    category: str = typer.Option(
        "tech",
        "--category",
        "-c",
        help="카테고리 id (categories.yaml 의 id 중 하나).",
    ),
    push: bool = typer.Option(
        True,
        "--push/--no-push",
        help="J-Blog 로 push 여부. --no-push 면 로컬에 파일만 작성.",
    ),
) -> None:
    """가짜 글 1편을 만들어 J-Blog 에 발행. 두 리포 자동화 흐름 검증용."""
    setup_logging()
    log = get_logger("cli.dry_run")

    settings = get_settings()
    log.info("dry_run.start",
             jblog=str(settings.jblog_abs_path()),
             push=push,
             dry_run_env=settings.dry_run)

    draft = ArticleDraft(
        title=title,
        body_markdown=_PLACEHOLDER_BODY,
        category=category,
        summary="scaffold 단계 검증용. 본문은 자동 생성기가 붙는 다음 단계에서 교체된다.",
        tags=["scaffold", "test"],
        sources=[
            SourceRef(
                url="https://github.com/haangman/blogMaker",
                title="blogMaker 리포지토리",
            ),
        ],
    )

    info = publish(draft, do_push=push)
    typer.secho(f"[OK]  글 작성: {info.post_path}", fg="green")
    if info.commit_sha:
        typer.secho(f"[OK]  commit: {info.commit_sha}", fg="green")
    if info.pushed:
        typer.secho("[OK]  push 완료 — GitHub Pages 빌드 후 1~2분 내 노출", fg="green")
        typer.echo("       https://haangman.github.io/J-Blog/")
    else:
        typer.secho("[--]  push 스킵 (로컬 파일만 작성)", fg="yellow")


@app.command()
def run(
    blog: list[str] = typer.Option(
        None, "--blog", "-b",
        help="특정 블로그만 실행 (예: --blog ai). 여러 번 가능. 기본은 enabled 전체.",
    ),
) -> None:
    """메인 사이클 1회 실행 (Task Scheduler 가 호출하는 것과 동일)."""
    from src.main import run_cycle

    rc = run_cycle(blog_ids=list(blog) if blog else None)
    raise typer.Exit(code=rc)


@app.command("analyze-persona")
def analyze_persona(
    urls: list[str] = typer.Option(
        ...,
        "--url",
        "-u",
        help="블로그/RSS URL. 여러 개 가능 (--url A --url B).",
    ),
    per_url_limit: int = typer.Option(20, help="URL 당 최대 분석 글 수"),
) -> None:
    """사용자 지정 한국 블로거 글을 분석해 persona.generated.md 자동 작성."""
    setup_logging()
    log = get_logger("cli.analyze_persona")
    log.info("persona.start", urls=urls)

    # 도메인별 그룹핑
    by_domain: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for u in urls:
        candidates = fetch_articles(u, limit=per_url_limit)
        log.info("persona.candidates", url=u, n=len(candidates))
        bodies = fetch_bodies(candidates[:per_url_limit])
        if not bodies:
            typer.secho(f"[WARN] {u} 에서 본문 추출 실패", fg="yellow")
            continue
        domain = urlparse(u).netloc or "unknown"
        save_samples(domain, bodies)
        by_domain[domain].extend(bodies)
        typer.echo(f"[OK]  {domain}: {len(bodies)} 편 수집")

    flat = [pair for items in by_domain.values() for pair in items]
    if not flat:
        typer.secho("[FAIL] 분석할 본문이 0편. URL 확인 필요.", fg="red")
        raise typer.Exit(code=1)

    typer.echo(f"분석 중... (총 {len(flat)} 편)")
    analyzed = persona_analyze(flat)
    if not analyzed:
        typer.secho("[FAIL] 분석 결과 비어 있음.", fg="red")
        raise typer.Exit(code=1)

    target, diff = save_generated(analyzed, sources=urls)
    typer.secho(f"[OK]  persona.generated.md 갱신: {target}", fg="green")
    if diff:
        typer.echo("\n--- diff ---")
        typer.echo(diff[:4000])


def main() -> None:
    app()


if __name__ == "__main__":
    main()
