"""이미지 첨부 — 헤더 1장(자동 키워드) + 본문 마커 0~3장.

`attach_images(article, cluster)` 가 ArticleDraft.images 리스트를 채운다.
첫 번째 항목이 헤더 이미지 (marker_keyword=None), 나머지는 본문 마커.
Unsplash/Pexels 키가 비어있어도 graceful — 아무것도 못 받으면 빈 리스트로 둠.
"""

from __future__ import annotations

from src.cluster.merge import TopicCluster
from src.config_loader import get_settings
from src.images import pexels, pollinations, unsplash
from src.images.markers import extract_markers, fetch_for_markers
from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger
from src.publisher.models import ArticleDraft, ImageRef

log = get_logger("images")


_KEYWORD_SYSTEM = (
    "한국어 블로그 글의 헤더에 쓸 영어 **스톡 사진 검색어**를 만든다.\n"
    "글 본문이 묘사한 한 가지 **구체적 시각 장면**을 영어로 옮긴 검색어 한 줄.\n"
    "\n"
    "규칙:\n"
    "- 영문 **3~5 단어**.\n"
    "- 명사를 중심으로 (형용사·장소·맥락 조합 OK). 추상 개념·감정·범주 단독 금지.\n"
    "- 본문이 묘사한 사물·인물·동물·풍경·소품·동작 중 **가장 시각화 가능한 것 1가지**.\n"
    "- 사진에 흔히 있을 법한 장면이어야 한다 (검색 결과 의외이지 않게).\n"
    "- 답은 검색어 한 줄. 다른 설명·따옴표·prefix 금지.\n"
    "\n"
    "좋은 예 (장면이 또렷이 떠오름):\n"
    "- silky anteater small mammal closeup\n"
    "- paper cutout silhouette in front of building\n"
    "- open pc case rgb fans desk\n"
    "- korean night street rainy neon\n"
    "- empty cafe table morning light\n"
    "\n"
    "나쁜 예 (장면이 모호하거나 스톡에 거의 없음):\n"
    "- 'rare animals surreal art' (추상)\n"
    "- 'innovation technology' (개념)\n"
    "- 'reddit homepage screen' (SNS 캡처 — 스톡엔 거의 없음)\n"
    "- 'atmosphere mood' (감정 단독)"
)


def _header_keywords(cluster: TopicCluster, body_excerpt: str = "") -> str:
    parts = [
        f"제목: {cluster.event_title}",
        f"요약: {cluster.event_summary}",
    ]
    if body_excerpt:
        parts.append("")
        parts.append("본문 도입부 (이걸 보고 어떤 장면을 그릴지 결정):")
        parts.append(body_excerpt.strip())
    user = "\n".join(parts)
    try:
        resp = ask(
            user,
            system_prompt=_KEYWORD_SYSTEM,
            model="opus",
            purpose="image_keywords",
            timeout_s=60,
        )
        kw = resp.text.strip().splitlines()[0].strip().strip('"\'')
        return kw or cluster.category
    except ClaudeCLIError:
        return cluster.category


def _try_fetch_one(query: str) -> ImageRef | None:
    """이미지 한 장. config 의 image_provider 에 따라 공급자 순서 분기.
       auto: pollinations → unsplash → pexels
       pollinations: pollinations 만
       unsplash: unsplash → pexels (AI 생성 안 함)
    """
    provider = (get_settings().image_provider or "auto").lower()
    result = None
    if provider == "pollinations":
        result = pollinations.search_and_download(query)
    elif provider == "unsplash":
        result = unsplash.search_and_download(query) or pexels.search_and_download(query)
    else:  # auto (기본)
        result = (
            pollinations.search_and_download(query)
            or unsplash.search_and_download(query)
            or pexels.search_and_download(query)
        )
    if not result:
        return None
    local_path, meta = result
    return ImageRef(
        local_path=local_path,
        alt=meta.get("alt") or query,
        credit=meta.get("credit") or "",
        credit_url=meta.get("credit_url") or "",
        marker_keyword=None,
    )


def attach_images(article: ArticleDraft, cluster: TopicCluster) -> None:
    """헤더 1장 + 본문 마커 이미지들을 article.images 에 채운다.

    - article.body_markdown 안의 `[IMAGE: "..."]` 마커들에서 키워드 추출
    - 본문 마커 이미지 수 상한 3장 (publisher 가 매칭 안 된 마커는 제거)
    """
    if not article.body_markdown:
        return

    images: list[ImageRef] = []
    used_keywords: set[str] = set()
    used_signatures: set[str] = set()

    def _signature(img: ImageRef) -> str:
        return f"{img.local_path.name if img.local_path else ''}|{img.credit}"

    # 헤더 이미지 (1장) — 글 도입부를 보고 키워드 결정 (장면 매칭 정확도 ↑)
    header_kw = _header_keywords(cluster, body_excerpt=article.body_markdown[:600])
    log.info("images.header_query", q=header_kw)
    header = _try_fetch_one(header_kw)
    if header:
        images.append(header)
        used_keywords.add(header_kw.lower())
        used_signatures.add(_signature(header))
    else:
        log.info("images.header_not_found", q=header_kw)

    # 본문 마커 이미지 (0~3장) — 헤더 키워드/사진과 중복 회피
    markers = extract_markers(article.body_markdown)
    log.info("images.markers_found", n=len(markers))
    body_images: list[ImageRef] = []
    for img in fetch_for_markers(markers, limit=5):
        kw = (img.marker_keyword or "").lower()
        sig = _signature(img)
        if kw and kw in used_keywords:
            log.info("images.body_dedup_keyword", keyword=kw)
            continue
        if sig in used_signatures:
            log.info("images.body_dedup_signature", keyword=kw)
            continue
        body_images.append(img)
        used_keywords.add(kw)
        used_signatures.add(sig)
        if len(body_images) >= 3:
            break
    images.extend(body_images)

    article.images = images
    log.info(
        "images.attached",
        total=len(images),
        header=1 if header else 0,
        body=len(body_images),
    )


# 하위 호환 — 기존 호출자가 있다면 attach_images 를 쓰도록 alias.
attach_image = attach_images


__all__ = ["attach_images", "attach_image"]
