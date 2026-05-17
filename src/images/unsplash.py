"""Unsplash 검색 API. 무료 access key 가 있어야 동작."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from src.config_loader import get_settings
from src.logging_setup import get_logger
from src.utils.http import make_client

log = get_logger("images.unsplash")

SEARCH_URL = "https://api.unsplash.com/search/photos"


def search_and_download(query: str) -> tuple[Path, dict] | None:
    settings = get_settings()
    if not settings.unsplash_access_key:
        return None
    try:
        with make_client(user_agent="blogmaker/0.1") as client:
            resp = client.get(
                SEARCH_URL,
                params={"query": query, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {settings.unsplash_access_key}"},
            )
            if resp.status_code != 200:
                log.warning("unsplash.search_failed", status=resp.status_code)
                return None
            results = resp.json().get("results", [])
            if not results:
                return None
            photo = results[0]
            dl_url = photo["urls"]["regular"]
            img = client.get(dl_url, follow_redirects=True)
            if img.status_code != 200:
                return None
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.write(img.content)
            tmp.close()

        attribution = {
            "credit": f"Photo by {photo['user']['name']} on Unsplash",
            "credit_url": photo["user"]["links"]["html"] + "?utm_source=blogmaker&utm_medium=referral",
            "alt": photo.get("alt_description") or query,
        }
        return Path(tmp.name), attribution
    except Exception as e:
        log.warning("unsplash.exception", error=str(e))
        return None
