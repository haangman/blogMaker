"""정규화 — RawItem → NormalizedItem 변환과 1차 디둡."""

from __future__ import annotations

from src.collectors.base import RawItem
from src.normalize.dedupe import dedupe
from src.normalize.item import NormalizedItem
from src.normalize.text_clean import detect_lang, extract_body


def normalize_one(raw: RawItem, *, fetch_body: bool = False) -> NormalizedItem:
    body = raw.body
    if fetch_body and not body and raw.url:
        body = extract_body(raw.url, fallback_summary=raw.summary)
    lang_basis = body or raw.summary or raw.title
    return NormalizedItem(
        source_id=raw.source_id,
        external_id=raw.external_id,
        url=raw.url,
        title=raw.title,
        body=body or raw.summary,
        lang=detect_lang(lang_basis),
        published_at=raw.published_at,
        extra=dict(raw.extra),
    )


def normalize_batch(raws: list[RawItem], *, fetch_body: bool = False) -> list[NormalizedItem]:
    items = [normalize_one(r, fetch_body=fetch_body) for r in raws]
    return dedupe(items)


__all__ = ["NormalizedItem", "RawItem", "normalize_one", "normalize_batch", "dedupe"]
