"""통계 기반 자연스러움 검사 — 문단 길이 분산·어휘 반복·자카드·어미 streak."""

from __future__ import annotations

import re
import statistics
from collections import Counter

from src.quality.rules import compiled_rules

_STOPWORDS = {
    "그리고", "그러나", "근데", "그래서", "하지만", "또", "또한",
    "그", "이", "저", "것", "수", "등", "더", "또는",
    "the", "and", "of", "to", "a", "in", "is", "it", "that",
}


def _paragraphs(body: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def _sentences(body: str) -> list[str]:
    parts = re.split(r"(?<=[\.\?\!다]|[다요죠])\s+", body)
    return [s.strip() for s in parts if s.strip()]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]{2,}|[0-9]{2,}|[가-힣]{2,}", text.lower())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def detect_stats_issues(body: str) -> list[str]:
    failures: list[str] = []
    rules = compiled_rules()
    stats_conf = rules["stats"]
    length_conf = rules["length"]

    n = len(body)
    if n < length_conf.get("min_chars", 300):
        failures.append(f"length:too_short ({n} chars)")
    if n > length_conf.get("max_chars", 2200):
        failures.append(f"length:too_long ({n} chars)")

    paras = _paragraphs(body)
    if len(paras) >= 3 and n >= stats_conf.get("paragraph_len_cv_exempt_below", 350):
        lens = [len(p) for p in paras]
        mean = statistics.mean(lens)
        std = statistics.pstdev(lens) if mean else 0.0
        cv = (std / mean) if mean else 0.0
        if cv < stats_conf.get("paragraph_len_cv_min", 0.35):
            failures.append(f"stats:uniform_paragraph_len (cv={cv:.2f})")

    toks = [t for t in _tokens(body) if t not in _STOPWORDS]
    total = len(toks) or 1
    counts = Counter(toks).most_common(10)
    block_ratio = stats_conf.get("token_ratio_block", 0.030)
    for tok, c in counts:
        ratio = c / total
        if ratio > block_ratio:
            failures.append(f"stats:repeat_token ({tok} {ratio:.1%})")
            break

    if len(paras) >= 2:
        first_set = set(_tokens(paras[0])) - _STOPWORDS
        last_set = set(_tokens(paras[-1])) - _STOPWORDS
        j = _jaccard(first_set, last_set)
        cap = stats_conf.get("first_last_paragraph_jaccard_max", 0.30)
        if j > cap and first_set and last_set:
            failures.append(f"stats:first_last_overlap (j={j:.2f})")

    # 같은 어미 연속 streak
    streak_cap = stats_conf.get("same_sentence_ending_streak_max", 5)
    sents = _sentences(body)
    if len(sents) >= streak_cap:
        last_endings = [s[-2:] for s in sents if len(s) >= 2]
        streak = 1
        prev = None
        for end in last_endings:
            if end == prev:
                streak += 1
                if streak >= streak_cap:
                    failures.append(f"stats:same_ending_streak ({end} x{streak})")
                    break
            else:
                streak = 1
                prev = end
    return failures


def must_contain_any_check(body: str) -> list[str]:
    rules = compiled_rules()
    pool = rules.get("must_contain_any", [])
    if not pool:
        return []
    if any(token in body for token in pool):
        return []
    return [f"persona:missing_signature_phrase (need any of {pool})"]


# `[IMAGE: "..."]` 마커 — quality 모듈에서 가볍게 카운팅용
_BODY_IMAGE_MARKER = re.compile(r'\[IMAGE:\s*"[^"]+"\s*\]')


def count_body_image_markers(body: str) -> int:
    return len(_BODY_IMAGE_MARKER.findall(body))
