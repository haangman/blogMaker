"""Collector 추상화 + RawItem 정의."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawItem:
    source_id: str
    external_id: str
    url: str
    title: str
    summary: str = ""
    body: str = ""
    published_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Collector(ABC):
    source_id: str

    def __init__(self, source_id: str, params: dict | None = None):
        self.source_id = source_id
        self.params = params or {}

    @abstractmethod
    def fetch(self) -> list[RawItem]:
        ...
