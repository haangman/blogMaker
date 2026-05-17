"""LLM 자동 시드 — 카테고리별 '꼭 정리해야 할' 토픽 N개 제안."""

from __future__ import annotations

import json
import re

from src.backlog.loader import insert_topics
from src.config_loader import CONFIG_DIR, load_yaml
from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger

log = get_logger("backlog.seed")


_SYSTEM = (
    "당신은 한국어 AI 기술 블로그를 운영합니다. 독자는 AI 개발자·관심자·기술을 처음 접하는 사람.\n"
    "사용자가 카테고리 1개를 알려주면, 그 카테고리에서 **꼭 정리되어야 할 핵심 토픽 N개**를 제안합니다.\n"
    "\n"
    "조건:\n"
    "- 각 토픽은 글 1편 분량으로 다룰 수 있는 단위 (너무 크지도, 너무 잘지도 않게).\n"
    "- 입문(intro) / 중급(intermediate) / 심화(deep) 골고루 섞기.\n"
    "- 같은 토픽의 변형 반복 금지 (예: 'Transformer 기초' 와 'Transformer 입문' 같은 중복).\n"
    "- 한국어 토픽명 (제목 형태, 마침표 X). 20자 내외 권장.\n"
    "- priority: 'high' 는 '이 카테고리에서 빠뜨리면 안 되는 기본기',\n"
    "  'medium' 은 '꽤 중요한 핵심',\n"
    "  'low' 는 '여유 있을 때 정리'.\n"
    "\n"
    "**출력 형식 — 정확히 이 JSON 배열만, 다른 설명 금지**:\n"
    "[\n"
    '  {\"topic\": \"...\", \"depth\": \"intro\", \"priority\": \"high\"},\n'
    '  {\"topic\": \"...\", \"depth\": \"intermediate\", \"priority\": \"medium\"},\n'
    "  ...\n"
    "]\n"
)


_JSON_ARRAY_RE = re.compile(r"\[\s*\{.*?\}\s*\]", re.DOTALL)


def _extract_json_array(text: str) -> list[dict]:
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return []
    raw = m.group(0)
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict) and d.get("topic")]
    except json.JSONDecodeError:
        log.warning("backlog.seed.json_parse_failed", preview=raw[:200])
    return []


def seed_for_category(category_id: str, label_ko: str, hints: str,
                      *, n: int = 30, blog_id: str = "ai") -> list[dict]:
    user = (
        f"카테고리 id: {category_id}\n"
        f"카테고리 한국어 이름: {label_ko}\n"
        f"카테고리 설명/힌트: {hints}\n"
        f"\n"
        f"이 카테고리에서 꼭 정리되어야 할 토픽 **{n}개** 를 JSON 배열로 제안하시오."
    )
    try:
        resp = ask(user, system_prompt=_SYSTEM, model="opus",
                   purpose="backlog_seed", timeout_s=240)
    except ClaudeCLIError as e:
        log.warning("backlog.seed.llm_failed", category=category_id, error=str(e))
        return []

    raw_topics = _extract_json_array(resp.text)
    out: list[dict] = []
    for t in raw_topics:
        topic = (t.get("topic") or "").strip()
        if not topic:
            continue
        out.append({
            "topic": topic,
            "category": category_id,
            "priority": t.get("priority", "medium"),
            "depth": t.get("depth", "intro"),
        })
    log.info("backlog.seed.category", category=category_id, n=len(out))
    return out


def seed_backlog(blog_id: str = "ai", *, categories_file: str = "categories.ai.yaml",
                 per_category: int = 30) -> int:
    """카테고리당 per_category 개 시드. 누적 inserted 수 반환.

    LLM 호출 ≈ 카테고리 수 (12개) — 1회 시드는 약 12 호출.
    """
    cats = load_yaml(categories_file).get("categories", [])
    if not cats:
        log.warning("backlog.seed.no_categories", file=categories_file)
        return 0

    total_inserted = 0
    for cat in cats:
        cid = cat["id"]
        if cid == "other":
            continue
        proposed = seed_for_category(
            cid, cat.get("label_ko", cid), cat.get("hints", ""),
            n=per_category, blog_id=blog_id,
        )
        if proposed:
            total_inserted += insert_topics(blog_id, proposed)
    log.info("backlog.seed.done", blog=blog_id, total_inserted=total_inserted)
    return total_inserted
