"""멀티 블로그 프로파일 로더.

각 블로그는 자신만의 리포·소스·카테고리·페르소나·selector 가중치를 갖는다.
한 blogMaker 가 여러 블로그를 순차로 처리.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from src.config_loader import CONFIG_DIR, REPO_ROOT, load_yaml


@dataclass
class BlogProfile:
    id: str
    enabled: bool
    name: str
    repo_path: str                 # 'blogMaker 기준 상대' or 절대
    repo_name: str                 # 'J-Blog' / 'J-Blog-AI' — publisher sanity 가드용
    baseurl: str
    sources_file: str              # 'sources.yaml' / 'sources.ai.yaml'
    categories_file: str
    persona_files: list[str]       # 합성 순서: generated 먼저, user 마지막 (우선)
    selector_profile: str          # 'lifestyle' | 'ai' | 'fashion'
    articles_per_cycle: int = 5
    backlog_file: str | None = None  # 'ai_backlog.yaml' or None
    backlog_ratio: float = 0.0       # 사이클당 글 중 백로그 비율 (0~1)
    theme: str = "minima"            # 'minima' | 'chirpy' | 'beautiful-jekyll' — publisher frontmatter 분기
    extras: dict = field(default_factory=dict)

    def repo_abs_path(self) -> Path:
        p = Path(self.repo_path)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()


_DEFAULT_BLOG = BlogProfile(
    id="trends",
    enabled=True,
    name="trend log",
    repo_path="../J-Blog",
    repo_name="J-Blog",
    baseurl="/J-Blog",
    sources_file="sources.yaml",
    categories_file="categories.yaml",
    persona_files=["persona.generated.md", "persona.md"],
    selector_profile="lifestyle",
    articles_per_cycle=5,
    backlog_file=None,
    backlog_ratio=0.0,
)


@lru_cache(maxsize=1)
def load_blogs() -> list[BlogProfile]:
    raw = load_yaml("blogs.yaml")
    if not raw or "blogs" not in raw:
        return [_DEFAULT_BLOG]
    out: list[BlogProfile] = []
    for entry in raw.get("blogs", []):
        out.append(
            BlogProfile(
                id=entry["id"],
                enabled=bool(entry.get("enabled", True)),
                name=entry.get("name", entry["id"]),
                repo_path=entry["repo_path"],
                repo_name=entry["repo_name"],
                baseurl=entry["baseurl"],
                sources_file=entry.get("sources_file", "sources.yaml"),
                categories_file=entry.get("categories_file", "categories.yaml"),
                persona_files=entry.get("persona_files",
                                       ["persona.generated.md", "persona.md"]),
                selector_profile=entry.get("selector_profile", "lifestyle"),
                articles_per_cycle=int(entry.get("articles_per_cycle", 5)),
                backlog_file=entry.get("backlog_file"),
                backlog_ratio=float(entry.get("backlog_ratio", 0.0)),
                theme=entry.get("theme", "minima"),
                extras=entry.get("extras") or {},
            )
        )
    return out


def for_id(blog_id: str) -> BlogProfile:
    for b in load_blogs():
        if b.id == blog_id:
            return b
    raise KeyError(f"blog id 없음: {blog_id}")


def enabled_blogs() -> list[BlogProfile]:
    return [b for b in load_blogs() if b.enabled]
