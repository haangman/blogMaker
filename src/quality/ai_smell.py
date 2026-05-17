"""정형구 / AI 티 / 금칙어 검출."""

from __future__ import annotations

import re

from src.quality.rules import compiled_rules


def detect_ai_smell(body: str) -> list[str]:
    rules = compiled_rules()
    failures: list[str] = []
    for pat in rules["ai_smell_patterns"]:
        m = pat.search(body)
        if m:
            failures.append(f"ai_smell:{pat.pattern} -> '{m.group(0)[:30]}'")
    for tok in rules["forbidden_first_person"]:
        # 단어 경계 — 한국어는 \b 가 잘 안 먹어서 인접 글자로 보강
        if re.search(rf"(?<![가-힣]){re.escape(tok)}(?=[는은가이의를을도만요?…\s\.\!])", body):
            failures.append(f"forbidden_first_person:{tok}")
    return failures
