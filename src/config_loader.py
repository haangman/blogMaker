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

    jblog_path: str = "../J-Blog"
    git_user_name: str = ""
    git_user_email: str = ""

    log_level: str = "INFO"
    dry_run: bool = False
    hf_home: str = ""
    max_daily_articles: int = 2

    claude_cli_path: str = "claude"
    claude_cli_timeout_sec: int = 180

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
