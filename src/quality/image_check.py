"""이미지 품질 게이트 — Pollinations 같은 생성 이미지가 토픽과 안 맞거나
인공 부산물이 있을 때 다음 provider 로 폴백하기 위한 평가기.

scripts/audit_ai_images.py 의 평가 logic 을 그대로 가져와 publisher 흐름에 통합.
한 사이클의 호출 폭주를 막기 위해:
- 캐시 (같은 alt + 같은 파일 sha 면 결과 재사용)
- LLM 호출은 첫 provider 결과만 검사 (Unsplash/Pexels 폴백은 재검사 안 함)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger

log = get_logger("quality.image")


_VISION_PROMPT_TEMPLATE = """다음 정보를 보고 이미지가 블로그 글에 사용하기 적합한지 평가해.

[글 제목] {title}
[글 요약] {summary}
[이미지 alt] {alt}
[이미지 파일] {image_path}

평가 기준:
1. 글의 토픽·분위기와 이미지가 어울리는가
2. 인공 부산물(왜곡된 사람 얼굴, 깨진 손가락, garbled 텍스트, 비현실적 합성, 색상 이상) 가 있는가

JSON 한 줄로만 응답 — 다른 설명 금지:
{{"ok": true|false, "reason": "한 줄"}}
"""


# 사이클 안에서 같은 (alt, file_sha) 조합은 한 번만 평가.
_CACHE: dict[tuple[str, str], bool] = {}


def _file_sha(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            h.update(f.read())
        return h.hexdigest()[:16]
    except Exception:
        return ""


def check_image(
    image_path: Path,
    *,
    title: str,
    summary: str = "",
    alt: str = "",
) -> tuple[bool, str]:
    """이미지가 글 토픽에 적합한지 평가. (ok, reason) 반환.

    실패 시 caller 가 다음 provider 로 폴백.
    """
    if not image_path or not Path(image_path).exists():
        return False, "missing_file"
    if not title:
        # 토픽 없으면 평가 불가 — 무조건 통과 (보수적)
        return True, "no_title_skip"

    key = (alt or "", _file_sha(Path(image_path)))
    if key in _CACHE:
        return _CACHE[key], "cache"

    prompt = _VISION_PROMPT_TEMPLATE.format(
        title=title,
        summary=(summary or "")[:280],
        alt=alt or "(alt 없음)",
        image_path=str(image_path),
    )
    try:
        resp = ask(prompt, model="opus", purpose="image_quality_gate", timeout_s=90)
    except ClaudeCLIError as e:
        log.warning("image_check.cli_error", error=str(e)[:200])
        # CLI 에러 시엔 통과 (가드는 게이트가 아닌 보조 신호)
        return True, "cli_error_passthrough"
    except Exception as e:
        log.warning("image_check.exception", error=str(e)[:200])
        return True, "exception_passthrough"

    text = (resp.text or "").strip()
    if "{" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    try:
        verdict = json.loads(text)
        ok = bool(verdict.get("ok"))
        reason = str(verdict.get("reason", ""))[:120]
    except Exception:
        log.warning("image_check.parse_failed", text=text[:120])
        ok = True   # 파싱 실패 시 통과 (false negative 보다 false positive 가 안전)
        reason = "parse_failed"

    _CACHE[key] = ok
    log.info("image_check.done", ok=ok, reason=reason, alt=alt[:60])
    return ok, reason


def clear_cache() -> None:
    """사이클 종료 시 호출 — 다음 사이클은 다시 평가."""
    _CACHE.clear()
