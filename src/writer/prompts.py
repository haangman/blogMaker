"""writer 시스템·유저 프롬프트 빌더.

페르소나(`config/persona.md` + `persona.generated.md`)와 품질 규칙을 합성.
사용자 편집 원본(persona.md)이 가장 마지막에 와서 우선순위가 높아진다.
"""

from __future__ import annotations

import random
from pathlib import Path

from src.cluster.merge import TopicCluster
from src.config_loader import CONFIG_DIR, load_quality_rules


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_system_prompt(*, rewrite_feedback: list[str] | None = None) -> str:
    persona_generated = _read_text(CONFIG_DIR / "persona.generated.md")
    persona_user = _read_text(CONFIG_DIR / "persona.md")

    rules = load_quality_rules()
    avoid = rules.get("ai_smell_patterns", [])
    forbidden_address = rules.get("person", {}).get("forbidden_address", [])
    must_contain = rules.get("must_contain_any", [])

    sections: list[str] = []
    sections.append(
        "너는 아래에 정의된 한 명의 한국어 블로거다. **그 사람으로서** 글을 쓴다.\n"
        "AI 가 쓴 티가 절대 나면 안 된다. 다음 가이드를 엄격히 지킨다:"
    )
    sections.append(
        "- 1인칭은 '나' (절대 '저' 금지)\n"
        f"- 호명 금지: {', '.join(forbidden_address) or '여러분'}\n"
        "- 다음 표현은 사용 금지:\n  " + "\n  ".join([f"· {p}" for p in avoid])
    )
    sections.append(
        "- 자주 쓰는 말투 풀에서 최소 1개는 자연스럽게 등장: "
        + ", ".join(must_contain)
    )
    sections.append(
        "- 문단 길이를 의도적으로 흔든다 (짧은 문장과 긴 문장 섞기)\n"
        "- 결론을 닫지 않고 열어두는 마무리 권장\n"
        "- 원문 직접 인용은 1문장 이내, 인용 시 `>` blockquote\n"
        "- 마크다운 본문만 출력. 프론트매터(`---`) 출력 금지. 제목(`#`) 금지 — 시스템이 별도 처리."
    )

    if persona_generated:
        sections.append("## 자동 분석된 톤 (보조)\n\n" + persona_generated)
    if persona_user:
        # 사용자 편집 원본이 마지막에 위치 — 충돌 시 우선
        sections.append("## 사용자 정의 페르소나 (우선)\n\n" + persona_user)

    if rewrite_feedback:
        sections.append(
            "## 직전 시도 게이트 실패 사유 — 반드시 반영해서 다시 써라\n"
            + "\n".join([f"- {x}" for x in rewrite_feedback])
        )

    return "\n\n".join(sections)


def build_user_prompt(cluster: TopicCluster) -> str:
    # 길이대 변주 — 매번 다른 분포
    lengths = [(450, 650), (700, 1000), (1000, 1400), (300, 450)]
    weights = [0.25, 0.4, 0.25, 0.10]
    lo, hi = random.choices(lengths, weights=weights, k=1)[0]

    excerpts = []
    for it in cluster.items[:5]:
        excerpt = (it.body or "")[:280].strip()
        excerpts.append(f"- ({it.source_id}) {it.title} — {excerpt}")

    return (
        f"카테고리: {cluster.category}\n"
        f"사건 제목(임시): {cluster.event_title}\n"
        f"사건 요약: {cluster.event_summary}\n\n"
        f"원문 발췌:\n" + "\n".join(excerpts) + "\n\n"
        f"위 사건을 본인의 시선으로 쓴 블로그 글로 풀어내라. "
        f"한국어 마크다운 본문, 대략 {lo}~{hi}자 사이. "
        f"제목 라인(`#`)은 절대 넣지 마. 본문만."
    )
