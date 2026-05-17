"""클러스터 요약을 categories.yaml 의 enum 중 하나로 분류."""

from __future__ import annotations

from src.config_loader import load_categories
from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger

log = get_logger("categorize")


def _build_system() -> str:
    cats = load_categories().get("categories", [])
    lines = []
    for c in cats:
        lines.append(f"- {c['id']} ({c.get('label_ko', '')}): {c.get('hints', '')}")
    enum = ", ".join([c["id"] for c in cats])
    return (
        "다음 사건 요약을 카테고리 중 하나로 분류한다. "
        f"가능한 id 만: {enum}. id 단어 하나만 출력. 다른 텍스트 금지.\n\n"
        "카테고리:\n" + "\n".join(lines)
    )


_SYSTEM_CACHE: str | None = None


def classify_category(title: str, summary: str) -> str:
    global _SYSTEM_CACHE
    if _SYSTEM_CACHE is None:
        _SYSTEM_CACHE = _build_system()
    valid = {c["id"] for c in load_categories().get("categories", [])}
    user = f"제목: {title}\n요약: {summary}"
    try:
        resp = ask(user, system_prompt=_SYSTEM_CACHE, model="opus", purpose="categorize")
    except ClaudeCLIError as e:
        log.warning("categorize.failed", error=str(e))
        return "other"
    raw = resp.text.strip().lower().split()[0] if resp.text.strip() else "other"
    return raw if raw in valid else "other"
