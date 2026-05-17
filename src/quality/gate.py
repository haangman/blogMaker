"""품질 게이트 종합 판정."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.config_loader import load_quality_rules
from src.logging_setup import get_logger
from src.quality.ai_smell import detect_ai_smell
from src.quality.persona_check import detect_persona_violations
from src.quality.stats import count_body_image_markers, detect_stats_issues

log = get_logger("quality.gate")

# ```lang ... ``` 코드 펜스 — 정형구/통계 검사 시 본문에서 제거 (mermaid·python 등 자연어 아님)
_CODE_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\n.*?\n```", re.DOTALL)


def _strip_code_fences(body: str) -> str:
    return _CODE_FENCE.sub("", body)


@dataclass
class GateResult:
    outcome: str             # 'pass' | 'fail'
    score: float             # 0.0~1.0 (1.0 = 무결점)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def evaluate(body: str) -> GateResult:
    # 코드 펜스(mermaid/python 등) 는 자연어 검사 대상이 아님 — 제거 후 검사
    natural = _strip_code_fences(body).strip()

    failures: list[str] = []
    failures.extend(detect_ai_smell(natural))
    failures.extend(detect_stats_issues(natural))
    failures.extend(detect_persona_violations(natural))

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
