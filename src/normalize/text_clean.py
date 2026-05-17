"""본문 추출 + 언어 감지."""

from __future__ import annotations

from src.logging_setup import get_logger

log = get_logger("normalize.text")


def detect_lang(text: str) -> str:
    """lingua 가 있으면 그걸로, 없거나 짧으면 'und'."""
    if not text or len(text) < 20:
        return "und"
    try:
        from lingua import IsoCode639_1, Language, LanguageDetectorBuilder

        detector = _get_detector()
        lang = detector.detect_language_of(text)
        return lang.iso_code_639_1.name.lower() if lang else "und"
    except Exception:
        return "und"


_DETECTOR = None


def _get_detector():
    global _DETECTOR
    if _DETECTOR is None:
        from lingua import Language, LanguageDetectorBuilder

        _DETECTOR = (
            LanguageDetectorBuilder.from_languages(
                Language.ENGLISH, Language.KOREAN, Language.JAPANESE, Language.CHINESE
            )
            .with_low_accuracy_mode()
            .build()
        )
    return _DETECTOR


def extract_body(url: str, fallback_summary: str = "") -> str:
    """원격 URL 에서 본문을 받아 trafilatura 로 추출. 실패하면 fallback 또는 빈 문자열."""
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return fallback_summary
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            favor_recall=False,
            no_fallback=False,
        )
        return text or fallback_summary
    except Exception as e:
        log.warning("trafilatura.extract_failed", url=url, error=str(e))
        return fallback_summary
