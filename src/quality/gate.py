"""품질 게이트 종합 판정."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config_loader import load_quality_rules
from src.logging_setup import get_logger
from src.quality.ai_smell import detect_ai_smell
from src.quality.persona_check import detect_persona_violations
from src.quality.stats import count_body_image_markers, detect_stats_issues

log = get_logger("quality.gate")


@dataclass
class GateResult:
    outcome: str             # 'pass' | 'fail'
    score: float             # 0.0~1.0 (1.0 = 무결점)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def evaluate(body: str) -> GateResult:
    failures: list[str] = []
    failures.extend(detect_ai_smell(body))
    failures.extend(detect_stats_issues(body))
    failures.extend(detect_persona_violations(body))

    # 이미지 마커 경고 (차단 X — INFO 로그만 + warnings 리스트)
    warnings: list[str] = []
    rules = load_quality_rules()
    img_min = (rules.get("images") or {}).get("min_in_body_when_long", 1)
    if img_min and len(body) >= 1500:
        n = count_body_image_markers(body)
        if n < img_min:
            warnings.append(f"images:few_body_markers (got {n}, expect ≥{img_min})")
            log.info("gate.image_marker_low", count=n, body_chars=len(body))

    # 단순 점수: 실패 개수에 비례해 감점
    score = max(0.0, 1.0 - 0.15 * len(failures))
    outcome = "pass" if not failures else "fail"
    return GateResult(outcome=outcome, score=score, failures=failures, warnings=warnings)
