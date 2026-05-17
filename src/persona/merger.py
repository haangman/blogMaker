"""분석 결과를 config/persona.generated.md 에 저장. 사용자 persona.md 는 건드리지 않는다."""

from __future__ import annotations

import difflib
from pathlib import Path

from src.config_loader import CONFIG_DIR
from src.logging_setup import get_logger
from src.utils.timeutil import iso_now

log = get_logger("persona.merger")


def save_generated(analyzed_md: str, *, sources: list[str]) -> tuple[Path, str]:
    """analyzed_md 를 persona.generated.md 에 저장. 이전 내용과의 diff 를 반환."""
    target = CONFIG_DIR / "persona.generated.md"
    previous = target.read_text(encoding="utf-8") if target.exists() else ""

    header = (
        "<!-- 자동 생성됨. 직접 편집 가능하지만 다음 analyze-persona 실행 시 덮어쓰임. -->\n"
        f"<!-- generated_at: {iso_now()} -->\n"
        + "".join([f"<!-- source: {s} -->\n" for s in sources])
        + "\n"
    )
    new_text = header + analyzed_md.strip() + "\n"
    target.write_text(new_text, encoding="utf-8")

    diff = "\n".join(
        difflib.unified_diff(
            previous.splitlines(),
            new_text.splitlines(),
            fromfile="persona.generated.md (이전)",
            tofile="persona.generated.md (신규)",
            lineterm="",
        )
    )
    log.info("persona.saved", path=str(target), diff_lines=len(diff.splitlines()))
    return target, diff
