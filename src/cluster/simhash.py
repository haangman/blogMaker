"""간단한 64비트 simhash (해밍거리 기반 사건 식별).

발행 이력 매칭의 안정적인 키. 클러스터 id 비결정성을 우회한다.
"""

from __future__ import annotations

import hashlib
import re


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    # 한·중·일 음절은 그대로 토큰화, 영문은 공백·기호 기준
    return re.findall(r"[A-Za-z]{2,}|[0-9]{2,}|[가-힣]{2,}|[ぁ-んァ-ンー一-龥]{1,}", text)


def simhash64(text: str) -> int:
    tokens = _tokenize(text)
    if not tokens:
        return 0
    bits = [0] * 64
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(64):
            bits[i] += 1 if (h >> i) & 1 else -1
    fp = 0
    for i in range(64):
        if bits[i] > 0:
            fp |= 1 << i
    return fp


def hamming(a: int, b: int) -> int:
    # 64bit 마스크 — signed/unsigned 변환 후에도 동일 비트 거리 보장
    return bin((a ^ b) & 0xFFFFFFFFFFFFFFFF).count("1")


def to_signed64(n: int) -> int:
    """SQLite INTEGER (signed 64bit) 저장용으로 unsigned 64bit 값을 변환."""
    if n is None:
        return None
    n = n & 0xFFFFFFFFFFFFFFFF
    return n - (1 << 64) if n >= (1 << 63) else n
