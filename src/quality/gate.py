"""품질 게이트 종합 판정."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.quality.ai_smell import detect_ai_smell
from src.quality.persona_check import detect_persona_violations
from src.quality.stats import detect_stats_issues


@dataclass
class GateResult:
    outcome: str             # 'pass' | 'fail'
    score: float             # 0.0~1.0 (1.0 = 무결점)
    failures: list[str] = field(default_factory=list)


def evaluate(body: str) -> GateResult:
    failures: list[str] = []
    failures.extend(detect_ai_smell(body))
    failures.extend(detect_stats_issues(body))
    failures.extend(detect_persona_violations(body))

    # 단순 점수: 실패 개수에 비례해 감점
    score = max(0.0, 1.0 - 0.15 * len(failures))
    outcome = "pass" if not failures else "fail"
    return GateResult(outcome=outcome, score=score, failures=failures)
