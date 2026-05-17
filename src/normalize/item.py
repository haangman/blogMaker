"""정규화된 항목 — 모든 collector 결과가 공통 형태로 모인다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NormalizedItem:
    source_id: str
    external_id: str
    url: str
    title: str
    body: str
    lang: str           # ISO 639-1, 모르면 'und'
    published_at: datetime | None
    extra: dict[str, Any] = field(default_factory=dict)
