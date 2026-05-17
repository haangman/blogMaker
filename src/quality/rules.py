"""quality_rules.yaml 로딩 + persona.md 의 '피하는 표현' 자동 합성."""

from __future__ import annotations

import re
from functools import lru_cache

from src.config_loader import CONFIG_DIR, load_quality_rules


@lru_cache(maxsize=1)
def compiled_rules() -> dict:
    rules = load_quality_rules()
    patterns = list(rules.get("ai_smell_patterns", []))
    person = rules.get("person", {})
    forbidden_address = person.get("forbidden_address", [])
    for w in forbidden_address:
        patterns.append(re.escape(w))

    # persona.md 안의 '피하는 표현' 섹션에서 bullet 추출
    persona_path = CONFIG_DIR / "persona.md"
    if persona_path.exists():
        text = persona_path.read_text(encoding="utf-8")
        # 간단한 섹션 파서
        in_section = False
        for line in text.splitlines():
            if "피하는 표현" in line:
                in_section = True
                continue
            if in_section:
                if line.startswith("## "):
                    break
                m = re.match(r"^- (.+?)$", line.strip())
                if m:
                    chunk = m.group(1).strip().strip('"\'`')
                    # 따옴표로 감싼 첫 토큰만 안전하게
                    for w in re.findall(r'"([^"]+)"', chunk):
                        patterns.append(re.escape(w))

    return {
        "ai_smell_patterns": [re.compile(p) for p in patterns],
        "forbidden_first_person": person.get("forbidden_first_person", ["저"]),
        "must_contain_any": rules.get("must_contain_any", []),
        "stats": rules.get("stats", {}),
        "length": rules.get("length", {"min_chars": 300, "max_chars": 2200}),
    }
