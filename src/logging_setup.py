"""structlog 기반 로깅 + 키 마스킹 + 파일 회전."""

from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path
from typing import Any

import structlog

from src.config_loader import LOG_DIR, get_settings

# 키 이름 매칭 — '_PATH' 같은 무관한 변수가 가려지는 사고 방지를 위해 단어 경계 사용
_SECRET_KEY_PATTERN = re.compile(
    r"(?:^|_)(?:KEY|TOKEN|SECRET|PASSWORD|PAT)(?:$|_)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERN = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|gho_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,})")


def _mask_secrets(_logger, _method_name, event_dict: dict[str, Any]) -> dict[str, Any]:
    for k, v in list(event_dict.items()):
        if isinstance(k, str) and _SECRET_KEY_PATTERN.match(k):
            event_dict[k] = "***"
            continue
        if isinstance(v, str) and _SECRET_VALUE_PATTERN.search(v):
            event_dict[k] = _SECRET_VALUE_PATTERN.sub("***", v)
    return event_dict


def setup_logging() -> None:
    settings = get_settings()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=LOG_DIR / "blogmaker.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler()

    logging.basicConfig(
        level=level,
        handlers=[file_handler, stream_handler],
        format="%(message)s",
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            _mask_secrets,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name) if name else structlog.get_logger()
