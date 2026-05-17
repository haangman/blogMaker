"""Pexels 검색 — Unsplash 폴백."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.config_loader import get_settings
from src.logging_setup import get_logger
from src.utils.http import make_client

log = get_logger("images.pexels")

SEARCH_URL = "https://api.pexels.com/v1/search"


def search_and_download(query: str) -> tuple[Path, dict] | None:
    settings = get_settings()
    if not settings.pexels_api_key:
        return None
    try:
        with make_client(user_agent="blogmaker/0.1") as client:
            resp = client.get(
                SEARCH_URL,
                params={"query": query, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": settings.pexels_api_key},
            )
            if resp.status_code != 200:
                log.warning("pexels.search_failed", status=resp.status_code)
                return None
            photos = resp.json().get("photos", [])
            if not photos:
                return None
            photo = photos[0]
            dl_url = photo["src"]["large"]
            img = client.get(dl_url, follow_redirects=True)
            if img.status_code != 200:
                return None
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.write(img.content)
            tmp.close()
        attribution = {
            "credit": f"Photo by {photo['photographer']} on Pexels",
            "credit_url": photo.get("photographer_url", ""),
            "alt": photo.get("alt", query),
        }
        return Path(tmp.name), attribution
    except Exception as e:
        log.warning("pexels.exception", error=str(e))
        return None
