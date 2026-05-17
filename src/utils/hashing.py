"""해시 유틸. Step 2에서는 슬러그 접미사용 짧은 해시.

Step 5에서 simhash가 도입되면 그쪽이 클러스터 매칭 키를, 이쪽은 슬러그 충돌 회피용으로 남는다.
"""

from __future__ import annotations

import hashlib


def short_hash(text: str, length: int = 6) -> str:
    """text를 md5로 hex화, 앞 length 글자 반환. slug 충돌 회피용."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:length]
