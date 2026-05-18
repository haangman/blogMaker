"""writer 시스템·유저 프롬프트 빌더.

페르소나(`config/persona.md` + `persona.generated.md`)와 품질 규칙을 합성.
사용자 편집 원본(persona.md)이 가장 마지막에 와서 우선순위가 높아진다.

V2 변경:
- 독자 친화 가이드 (배경 설명·비유·짧은 예시) — 단, 매뉴얼체는 여전히 금지
- 길이 분포 상향 (800~2400자 위주)
- 본문 내 이미지 마커 `[IMAGE: "..."]` 사용 안내
"""

from __future__ import annotations

import random
from pathlib import Path

from src.blogs import BlogProfile
from src.cluster.merge import TopicCluster
from src.config_loader import CONFIG_DIR, load_quality_rules
from src.selector.followup import FollowupContext


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_system_prompt(
    *,
    rewrite_feedback: list[str] | None = None,
    blog: BlogProfile | None = None,
) -> str:
    if blog is None:
        from src.blogs import for_id
        try:
            blog = for_id("trends")
        except KeyError:
            from src.blogs import _DEFAULT_BLOG
            blog = _DEFAULT_BLOG

    persona_texts: list[tuple[str, str]] = []
    for pf in blog.persona_files:
        text = _read_text(CONFIG_DIR / pf)
        if text:
            persona_texts.append((pf, text))

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
        "[페르소나 강제]\n"
        "- 1인칭은 '나' (절대 '저' 금지)\n"
        f"- 호명 금지: {', '.join(forbidden_address) or '여러분'}\n"
        "- 다음 표현은 사용 금지:\n  " + "\n  ".join([f"· {p}" for p in avoid])
    )
    sections.append(
        "- 자주 쓰는 말투 풀에서 최소 1개는 자연스럽게 등장: "
        + ", ".join(must_contain)
    )
    sections.append(
        "[독자 친화 — 사람들이 잘 이해할 수 있게]\n"
        "- 독자가 토픽 배경을 모를 수도 있다고 가정한다. 처음 등장하는 고유명사·전문 용어는 한 줄로 자연스럽게 풀어준다 "
        "(예: \"OpenAI 의 ChatGPT — 작년부터 일반인도 막 쓰는 그 챗봇 — 이…\" 처럼).\n"
        "- 비유·구체적 숫자·짧은 일상 예시를 1~2개 끼워 넣어 사람 머릿속에 그림이 그려지게.\n"
        "- '왜 이게 중요한지 / 내 생활에 어떻게 닿는지' 를 본문 어딘가에서 한 번 짚는다.\n"
        "- **글의 첫 1~2 문장에는 그 글의 핵심 키워드/주제어가 자연스럽게 등장**해야 한다. "
        "검색 결과 미리보기에 보이는 부분이라, 풍경 묘사·비유로만 시작하면 검색에서 잡히지 않는다. "
        "다만 키워드 stuffing 금지 — 사람이 쓴 듯 한 번 자연스럽게 포함하는 정도.\n"
        "- 단, 매뉴얼체('~할 수 있습니다', '~하시면 됩니다') 는 여전히 금지. "
        "친절함은 매뉴얼체가 아니라 **친한 후배에게 카톡으로 풀어 설명하는 거리감** 이다.\n"
        "- 한 문단이 한 가지 생각을 담도록 자르고, 끊어 읽기 좋게.\n"
        "- 문단 길이를 의도적으로 흔든다 (짧은 문장과 긴 문장 섞기).\n"
        "- 결론을 닫지 않고 열어두는 마무리 권장.\n"
        "- 원문 직접 인용은 1문장 이내, 인용 시 `>` blockquote.\n"
        "- 마크다운 본문만 출력. 프론트매터(`---`) 출력 금지. 제목(`#`) 금지 — 시스템이 별도 처리.\n"
        "- **메타 라벨 금지**: '본문 작성합니다', '본문:', '여기 작성', '다음과 같이', '아래는' 같은 머리말/안내 문장을 본문 앞에 절대 붙이지 않는다. 곧장 글 첫 문장으로 시작."
    )
    sections.append(
        "[이미지 마커 — 본문 안에 자연스럽게]\n"
        "글 흐름이 한 번 끊기는 자리(섹션 전환점)에서 사진이 들어가면 독자 이해에 도움 되겠다 싶으면, "
        "그 자리에 다음 형식 마커를 **한 줄로 단독** 삽입해라:\n\n"
        '    [IMAGE: "english search query"]\n\n'
        "**마커 검색어 규칙 — 매우 중요. 안 지키면 엉뚱한 사진이 박힌다.**\n"
        "- 영문 **3~5 단어**.\n"
        "- 마커 자리에서 **방금 본문이 묘사한 구체적 시각 장면** 을 그대로 가리켜라. "
        "마커 직전 1~2 문단에 등장한 사물·인물·동물·풍경·소품·동작 중 "
        "사진으로 찍을 수 있는 가장 또렷한 한 장면.\n"
        "- 형태: **명사 중심 + 형용사 + 장소/맥락**. 추상 개념·감정·범주 단독 금지.\n"
        "- 같은 글의 마커들은 시각적으로 서로 **다른 장면**.\n"
        "- 마커 수는 본문 길이에 비례: 800자 이하 1개, 1500자 내외 2개, 2000자 이상 3개. 4개 이상 금지.\n"
        "- 마커가 본문 첫 줄/마지막 줄에 오면 어색 — 본문 **중간** 에만.\n"
        "- 마커 앞뒤로 빈 줄.\n"
        "\n"
        "좋은 예 (글 흐름과 매칭):\n"
        "- 본문이 '실키 안테이터 영상' 을 막 말한 자리:\n"
        '    [IMAGE: "silky anteater small mammal closeup"]\n'
        "- 본문이 '종이 오려 도시 풍경에 합성한 사진' 을 말한 자리:\n"
        '    [IMAGE: "paper cutout silhouette in front of building"]\n'
        "- 본문이 '직접 조립한 PC 부품 자랑' 을 말한 자리:\n"
        '    [IMAGE: "open pc case rgb fans desk"]\n'
        "- 본문이 '비 오는 서울 골목' 을 말한 자리:\n"
        '    [IMAGE: "rainy seoul alley night neon"]\n'
        "\n"
        "나쁜 예 (장면이 모호하거나 스톡에 거의 없음):\n"
        '- [IMAGE: "rare animals surreal art"]   ← 추상 형용사 위주\n'
        '- [IMAGE: "reddit homepage screen"]      ← SNS 캡처는 스톡 사진에 없음\n'
        '- [IMAGE: "innovation technology"]       ← 개념 단어\n'
        '- [IMAGE: "atmosphere mood"]             ← 감정·분위기 단독'
    )

    # AI 블로그용 추가 — mermaid 다이어그램 + 코드 펜스 가이드
    if blog.id == "ai":
        sections.append(
            "[AI 기술 다이어그램 — mermaid]\n"
            "기술 흐름·관계·구조를 그림으로 보이면 이해가 빨라질 자리에서는 "
            "마크다운 mermaid 코드블록을 본문에 직접 삽입해라:\n\n"
            "    ```mermaid\n"
            "    graph LR\n"
            "      User --> Encoder\n"
            "      Encoder --> Attention\n"
            "      Attention --> Decoder\n"
            "      Decoder --> Output\n"
            "    ```\n\n"
            "- 한 글에 다이어그램 **0~2개**. 너무 많으면 산만.\n"
            "- 박스+화살표 그래프 / 시퀀스 다이어그램 / 플로우차트 위주.\n"
            "- 한국어 라벨 OK (mermaid 가 한글 지원).\n"
            "- 다이어그램이 글 흐름과 직접 연결되지 않으면 차라리 빼라.\n"
            "\n"
            "[코드 스니펫]\n"
            "- 짧은 함수·CLI 명령·yaml 한 토막 정도. 30 줄 넘으면 의미 약해진다.\n"
            "- 언어 명시: ```python ```bash ```yaml ```mermaid.\n"
            "- 가짜 코드 만들지 마. 본인이 정말 돌려보지 않은 코드는 적당히 둘러대지 말고 '의사 코드' 라고 명시."
        )

    # 페르소나 — 분석된 톤(보조) 먼저, 사용자 정의(우선) 나중
    # blog.persona_files 의 순서 그대로 → 마지막이 우선
    n_persona = len(persona_texts)
    for i, (fname, text) in enumerate(persona_texts):
        label = "자동 분석된 톤 (보조)" if i < n_persona - 1 else "사용자 정의 페르소나 (우선)"
        sections.append(f"## {label} — `{fname}`\n\n{text}")

    if rewrite_feedback:
        sections.append(
            "## 직전 시도 게이트 실패 사유 — 반드시 반영해서 다시 써라\n"
            + "\n".join([f"- {x}" for x in rewrite_feedback])
        )

    return "\n\n".join(sections)


def build_user_prompt(
    cluster: TopicCluster,
    followup: FollowupContext | None = None,
    *,
    blog: BlogProfile | None = None,
) -> str:
    # 길이대 변주 — V2 에서 분포 상향
    lengths = [(800, 1200), (1200, 1700), (1700, 2400)]
    weights = [0.30, 0.45, 0.25]
    lo, hi = random.choices(lengths, weights=weights, k=1)[0]

    excerpts = []
    for it in cluster.items[:5]:
        excerpt = (it.body or "")[:280].strip()
        excerpts.append(f"- ({it.source_id}) {it.title} — {excerpt}")

    is_backlog = not cluster.items
    if is_backlog:
        parts = [
            f"카테고리: {cluster.category}",
            f"이번 글의 주제: **{cluster.event_title}**",
            f"메모: {cluster.event_summary}",
            "",
            "이건 외부 사건 정리가 아니라 **AI 기술의 핵심 주제를 처음 정리하는 글** 이다. "
            "독자가 이 주제를 처음 접해도 끝까지 따라올 수 있게 친절하게 — 그러나 "
            "매뉴얼체는 금지. 본인이 직접 만져본 한에서, 정확하지 않은 부분은 추측이라고 명시하면서.",
            "",
        ]
    else:
        parts = [
            f"카테고리: {cluster.category}",
            f"사건 제목(임시): {cluster.event_title}",
            f"사건 요약: {cluster.event_summary}",
            "",
            "원문 발췌:",
            *excerpts,
            "",
        ]

    if followup:
        parts.append(
            "[FOLLOW-UP] 같은 흐름을 이전에 한 번 다뤘다. "
            f"이전 글 제목: \"{followup.previous_title}\". "
            "이번 글은 그 글의 단순 반복이 아니라 **그 사이의 변화·새로 드러난 사실·달라진 분위기** 에 초점. "
            "이전 글의 결론을 그대로 끌어다 쓰지 마. "
            "본문 어딘가에서 자연스럽게 이전 글을 한 줄 정도 참조해도 좋다."
        )
        parts.append("")

    parts.append(
        f"위 사건을 본인의 시선으로 쓴 블로그 글로 풀어내라. "
        f"한국어 마크다운 본문, 대략 {lo}~{hi}자 사이. "
        f"본문 중간에 `[IMAGE: \"...\"]` 마커를 길이에 맞춰 1~3개 삽입. "
        f"제목 라인(`#`)은 절대 넣지 마. 본문만."
    )
    return "\n".join(parts)
