"""tenacity 기반 표준 재시도 데코레이터."""

from __future__ import annotations

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


def standard_retry(exc_types: type[BaseException] | tuple[type[BaseException], ...] = Exception):
    """3회, 지수 백오프 (1초, 2초, 4초). 외부 IO 호출 표준."""
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(exc_types),
        reraise=True,
    )
