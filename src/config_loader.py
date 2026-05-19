"""환경변수와 YAML 설정 일괄 로드 + 검증.

`pydantic-settings`가 .env를 자동 로드하고 타입 검증을 fail-fast로 잡는다.
YAML은 따로 로드해 dict로 반환 — 코드 변경 없이 소스/카테고리/규칙을 갱신할 수 있게.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"
LOG_DIR = REPO_ROOT / "logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    unsplash_access_key: str = ""
    pexels_api_key: str = ""
    reddit_user_agent: str = "blogmaker/0.1"

    # 이미지 공급자 우선순위.
    #   auto         — pollinations(AI 생성) → unsplash → pexels (기본)
    #   pollinations — Pollinations 만 사용 (실패 시 이미지 없음)
    #   unsplash     — Unsplash → Pexels (기존 동작, AI 생성 안 함)
    image_provider: str = "auto"

    jblog_path: str = "../J-Blog"
    git_user_name: str = ""
    git_user_email: str = ""

    log_level: str = "INFO"
    dry_run: bool = False
    hf_home: str = ""
    max_daily_articles: int = 2

    claude_cli_path: str = "claude"
    claude_cli_timeout_sec: int = 180
    # 한 사이클 내 LLM 호출 횟수 상한 — 의도치 않은 폭주(예: 클러스터 폭증) 보호.
    # 구독 quota 보호용. 비용($) 가드 아님.
    max_llm_calls_per_cycle: int = 80
    # 한 사이클에 발행할 글 수
    articles_per_cycle: int = 5
    # 발행 이력 중복 가드 윈도우 (일). 이 기간 안에 발행된 글과 simhash 매치 시 드롭
    duplicate_window_days: int = 30

    def jblog_abs_path(self) -> Path:
        p = Path(self.jblog_path)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_sources() -> dict:
    return load_yaml("sources.yaml")


def load_categories() -> dict:
    return load_yaml("categories.yaml")


def load_quality_rules() -> dict:
    return load_yaml("quality_rules.yaml")
