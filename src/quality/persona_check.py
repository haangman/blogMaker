"""페르소나 호환 — 1인칭 어휘, 호명, 필수 표현 등 (ai_smell/stats 와 보완 관계)."""

from __future__ import annotations

from src.quality.stats import must_contain_any_check


def detect_persona_violations(body: str) -> list[str]:
    failures: list[str] = []
    failures.extend(must_contain_any_check(body))
    return failures
