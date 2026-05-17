"""수집된 블로거 글들에서 톤·문체·자주 쓰는 표현을 추출."""

from __future__ import annotations

from src.llm import ask
from src.logging_setup import get_logger

log = get_logger("persona.analyzer")

_SYSTEM = """\
너는 한국어 블로그 글의 톤·문체를 분석하는 분석가다.
사용자가 여러 글의 본문을 묶어서 줄 거다.

다음을 추출해서 **그대로 마크다운으로** 응답해라. 다른 설명 금지.
구조는 아래 그대로 유지.

```
## 기본 프로필 (추정)
- 톤 키워드 5개: ...
- 1인칭/2인칭 비율과 호명 어휘: ...
- 문장 평균 길이대와 분산: ...

## 자주 쓰는 표현 (빈도 top 15, 한 줄에 하나씩)
- "..."
...

## 자주 쓰는 글 끝맺음/연결어
- ...

## 대조군 부재 — 일반 블로그에 흔한데 이 글엔 드문 표현
- ...

## 글 구조 패턴
- 도입부 유형: ...
- 본문 전개: ...
- 마무리 유형: ...

## 화자가 절대 안 쓸 것 같은 표현 (추정)
- ...
```

분석할 때 주의:
- 글 자체의 화자가 1인칭인지 3인칭 칼럼인지 먼저 구분.
- 단순 빈도 표현(그리고/하지만)은 무시. 그 화자만의 색이 보이는 표현 위주.
- 추정치는 추정임을 명시 ("~로 보인다", "~인 듯").
"""


def analyze(samples: list[tuple[str, str]]) -> str:
    if not samples:
        return ""
    blocks = []
    for title, body in samples[:20]:
        blocks.append(f"### {title}\n{body[:1500]}\n")
    user = "다음 글들을 분석해라.\n\n" + "\n---\n".join(blocks)
    resp = ask(user, system_prompt=_SYSTEM, model="opus", purpose="persona_analyze")
    return resp.text.strip()
