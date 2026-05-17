"""사용자가 제공한 URL 들에서 블로거 글 N편을 본문으로 수집."""

from __future__ import annotations

from urllib.parse import urlparse

import feedparser

from src.config_loader import DATA_DIR
from src.logging_setup import get_logger
from src.normalize.text_clean import extract_body
from src.utils.http import make_client

log = get_logger("persona.fetcher")


def _looks_like_feed(url: str) -> bool:
    return any(seg in url.lower() for seg in ("rss", "atom", "feed"))


def _try_feed(url: str, limit: int) -> list[tuple[str, str]]:
    parsed = feedparser.parse(url)
    if not parsed.entries:
        return []
    out: list[tuple[str, str]] = []
    for entry in parsed.entries[:limit]:
        link = entry.get("link") or ""
        if link:
            out.append((link, entry.get("title", "")))
    return out


def _try_sitemap(url: str, limit: int) -> list[tuple[str, str]]:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    with make_client() as client:
        for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-1.xml"):
            try:
                resp = client.get(base + path)
                if resp.status_code != 200:
                    continue
                # 매우 단순한 <loc> 추출
                from xml.etree import ElementTree as ET

                root = ET.fromstring(resp.text)
                ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
                locs = [el.text for el in root.iter(f"{ns}loc") if el.text]
                # 글로 보일 만한 URL 우선 필터 (간단 휴리스틱)
                article_like = [u for u in locs if any(s in u for s in ("/post", "/article", "/202", "/blog"))]
                cand = article_like or locs
                return [(u, "") for u in cand[:limit]]
            except Exception:
                continue
    return []


def fetch_articles(url: str, limit: int = 20) -> list[tuple[str, str]]:
    """URL 에서 본문 URL N개 후보를 만든다. 각 항목은 (url, title) 튜플."""
    if _looks_like_feed(url):
        out = _try_feed(url, limit)
        if out:
            return out
    # 본문 페이지 자체일 수도 있음 — 그것만 단일 항목
    candidates = _try_sitemap(url, limit)
    if not candidates:
        candidates = [(url, "")]
    return candidates


def fetch_bodies(urls_and_titles: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """(url, title) 리스트를 받아 본문을 추출한 (title, body) 리스트로."""
    bodies: list[tuple[str, str]] = []
    for url, title in urls_and_titles:
        body = extract_body(url, fallback_summary="")
        if body and len(body) > 200:
            bodies.append((title or url, body))
    return bodies


def save_samples(domain: str, items: list[tuple[str, str]]) -> None:
    out_dir = DATA_DIR / "persona_samples" / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, (title, body) in enumerate(items, start=1):
        (out_dir / f"{i:02d}.txt").write_text(
            f"# {title}\n\n{body}", encoding="utf-8"
        )
    log.info("persona.samples_saved", domain=domain, n=len(items))
