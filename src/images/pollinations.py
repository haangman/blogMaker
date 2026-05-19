"""Pollinations.ai 이미지 생성. 무료 + 키 불필요 + Flux 1 모델.

GET https://image.pollinations.ai/prompt/{prompt}?width=...&height=...
응답이 이미지 바이트 그대로라 다운로드가 단순. nologo=true 로 워터마크 제거,
private=true 로 공개 갤러리 노출 안 함.

unsplash.py 와 같은 시그너처를 따라 (Path, attribution) 반환.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from src.logging_setup import get_logger

log = get_logger("images.pollinations")

ENDPOINT = "https://image.pollinations.ai/prompt"
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 630
DEFAULT_MODEL = "flux"

# 검색어를 더 사진다운 결과로 만들기 위한 suffix.
# - photo realistic + editorial 톤 → 잡지 사진 느낌
# - no text / no watermark — Pollinations 가 종종 텍스트 합성을 시도해 제거.
PROMPT_SUFFIX = (
    "editorial photography, photorealistic, natural lighting, "
    "high detail, magazine quality, no text, no watermark"
)

# 실존 인물 사진은 초상권 이슈 → 프롬프트 단계에서 회피 키워드.
NEGATIVE_TERMS = "no human faces, no celebrities, no recognizable persons"


def _build_prompt(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return ""
    return f"{q}, {PROMPT_SUFFIX}, {NEGATIVE_TERMS}"


def _seed(query: str) -> int:
    # 같은 쿼리는 같은 이미지 — 재발행 시 다른 사진이 나오는 혼란 회피.
    h = hashlib.sha256(query.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big")


def search_and_download(query: str) -> tuple[Path, dict] | None:
    """query 기반으로 Pollinations 에 이미지 생성 요청 후 임시 파일로 다운로드.

    반환 형식은 unsplash.search_and_download 와 동일 — (Path, attribution dict).
    """
    if not query or not query.strip():
        return None
    prompt = _build_prompt(query)
    if not prompt:
        return None

    url = (
        f"{ENDPOINT}/{quote_plus(prompt)}"
        f"?width={DEFAULT_WIDTH}&height={DEFAULT_HEIGHT}"
        f"&model={DEFAULT_MODEL}&nologo=true&private=true&safe=true&seed={_seed(query)}"
    )

    try:
        # Pollinations 는 합성 시간이 5~15s 정도. 큰 timeout 필요 — 기본 http client 와 별도.
        timeout = httpx.Timeout(120.0, connect=10.0, read=120.0)
        with httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "blogmaker/0.1"},
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                log.warning("pollinations.failed", status=resp.status_code, query=query)
                return None
            ctype = resp.headers.get("content-type", "")
            if "image" not in ctype:
                log.warning("pollinations.not_image", ctype=ctype, query=query)
                return None
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.write(resp.content)
            tmp.close()
    except Exception as e:
        log.warning("pollinations.exception", error=str(e), query=query)
        return None

    attribution = {
        # 라이선스 정책상 attribution 의무는 없지만, AI 생성 이미지임을 표시 (정직성).
        "credit": "AI generated (Pollinations · Flux)",
        "credit_url": "https://pollinations.ai/",
        "alt": query,
    }
    return Path(tmp.name), attribution
