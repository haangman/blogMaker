"""quality.gate 회귀 — 정형구가 명확히 차단되는지, 자연스러운 글이 통과하는지."""

from __future__ import annotations

from src.quality.gate import evaluate


def _join(body_paragraphs: list[str]) -> str:
    return "\n\n".join(body_paragraphs)


def test_typical_ai_phrase_blocked():
    body = _join([
        "오늘은 인공지능 트렌드에 대해 알아보겠습니다.",
        "사실은 이런 흐름이 한두 달 사이에 바뀐 게 좀 흥미롭다.",
        "결론적으로 누구나 한 번 정도는 이 변화를 따라가야 할 것이다.",
    ])
    r = evaluate(body)
    assert r.outcome == "fail"
    assert any("ai_smell" in f for f in r.failures)


def test_too_short_blocked():
    r = evaluate("짧은 한 줄짜리 글이라 통과하면 안 된다.")
    assert r.outcome == "fail"
    assert any("length" in f for f in r.failures)


def test_address_words_blocked():
    body = _join([
        "사실은 이번 주에 본 장면 하나가 머릿속에 계속 맴돈다.",
        "거기엔 여러분이 모두 공감할 만한 지점이 있었다.",
        "이게 좀 웃긴 건 그 장면이 누가 봐도 단순한데, 단순함이 정확히 뭘 건드린 건지가 잘 안 잡힌다는 거다.",
        "이런 게 점점 더 자주 보인다는 건, 이전과 다른 결의 무언가가 흘러간다는 신호일지도.",
    ])
    r = evaluate(body)
    assert any("여러분" in f or "ai_smell" in f for f in r.failures)


def test_repeated_token_warning_or_block():
    word = "인공지능"
    body = _join([
        f"{word}이 다시 화제다. 사실은 이번 주만 해도 {word} 얘기를 세 번은 본 것 같다.",
        f"{word}, {word}, {word}, {word}, {word}, {word}, {word}, {word}, {word}.",
        "이게 좀 웃긴 게, 단어 자체보다 그 단어가 자리한 맥락이 흥미롭다.",
        "그래서 한 발 떨어져서 본다.",
    ])
    r = evaluate(body)
    assert r.outcome == "fail"
    assert any("repeat_token" in f for f in r.failures)


def test_natural_passes_basic_checks():
    body = _join([
        "어제저녁에 라디오에서 들은 곡 한 줄이 자꾸 걸린다.",
        "사실은 그렇게 특별한 가사도 아니었는데, "
        "이상하게 새벽에 들으면 다른 의미로 들리는 부분이 있었다. "
        "근데 한 번 더 들어보면 또 평범하다.",
        "이게 좀 웃긴 게, 노래는 그대로인데 듣는 시간대마다 다른 모양으로 도착한다. "
        "그건 노래의 성질일까, 듣는 사람의 성질일까. "
        "둘 다라는 답은 너무 쉬워서 별로 매력이 없다.",
        "오늘은 둘 다라는 답을 잠시 미뤄두기로 한다.",
    ])
    r = evaluate(body)
    # 정형구/금칙어가 없으니 ai_smell 항목은 비어야 함
    assert not any(f.startswith("ai_smell") for f in r.failures)
    # must_contain_any 후보(사실은/이게 좀)가 들어있으니 persona check 통과
    assert not any(f.startswith("persona:") for f in r.failures)
