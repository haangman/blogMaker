"""클러스터 요약을 카테고리 enum 중 하나로 분류."""

from __future__ import annotations

from functools import lru_cache

from src.config_loader import load_categories, load_yaml
from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger

log = get_logger("categorize")


def _build_system(categories_file: str) -> str:
    if categories_file == "categories.yaml":
        cats = load_categories().get("categories", [])
    else:
        cats = load_yaml(categories_file).get("categories", [])
    lines = []
    for c in cats:
        lines.append(f"- {c['id']} ({c.get('label_ko', '')}): {c.get('hints', '')}")
    enum = ", ".join([c["id"] for c in cats])
    return (
        "다음 사건 요약을 카테고리 중 하나로 분류한다. "
        f"가능한 id 만: {enum}. id 단어 하나만 출력. 다른 텍스트 금지.\n\n"
        "카테고리:\n" + "\n".join(lines)
    )


@lru_cache(maxsize=4)
def _system_cache(categories_file: str) -> tuple[str, frozenset[str]]:
    sys_prompt = _build_system(categories_file)
    if categories_file == "categories.yaml":
        cats = load_categories().get("categories", [])
    else:
        cats = load_yaml(categories_file).get("categories", [])
    valid = frozenset(c["id"] for c in cats)
    return sys_prompt, valid


def classify_category(
    title: str,
    summary: str,
    *,
    categories_file: str = "categories.yaml",
) -> str:
    sys_prompt, valid = _system_cache(categories_file)
    user = f"제목: {title}\n요약: {summary}"
    try:
        resp = ask(user, system_prompt=sys_prompt, model="opus", purpose="categorize")
    except ClaudeCLIError as e:
        log.warning("categorize.failed", error=str(e))
        return "other"
    raw = resp.text.strip().lower().split()[0] if resp.text.strip() else "other"
    return raw if raw in valid else "other"
