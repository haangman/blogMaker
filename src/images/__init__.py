"""이미지 첨부 — 헤더 1장(자동 키워드) + 본문 마커 0~3장.

`attach_images(article, cluster)` 가 ArticleDraft.images 리스트를 채운다.
첫 번째 항목이 헤더 이미지 (marker_keyword=None), 나머지는 본문 마커.
Unsplash/Pexels 키가 비어있어도 graceful — 아무것도 못 받으면 빈 리스트로 둠.
"""

from __future__ import annotations

from src.cluster.merge import TopicCluster
from src.images import pexels, unsplash
from src.images.markers import extract_markers, fetch_for_markers
from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger
from src.publisher.models import ArticleDraft, ImageRef

log = get_logger("images")


_KEYWORD_SYSTEM = (
    "사건 요약을 받아서 이미지 스톡 사이트(Unsplash) 검색용 영문 키워드 2~3 단어를 "
    "한 줄로만 답한다. 다른 설명 금지. 예: 'remote work laptop' 같은 식."
)


def _header_keywords(cluster: TopicCluster) -> str:
    user = f"제목: {cluster.event_title}\n요약: {cluster.event_summary}"
    try:
        resp = ask(
            user,
            system_prompt=_KEYWORD_SYSTEM,
            model="haiku",
            purpose="image_keywords",
            timeout_s=60,
        )
        kw = resp.text.strip().splitlines()[0].strip()
        return kw or cluster.category
    except ClaudeCLIError:
        return cluster.category


def _try_fetch_one(query: str) -> ImageRef | None:
    result = unsplash.search_and_download(query) or pexels.search_and_download(query)
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

    # 헤더 이미지 (1장)
    header_kw = _header_keywords(cluster)
    log.info("images.header_query", q=header_kw)
    header = _try_fetch_one(header_kw)
    if header:
        images.append(header)
    else:
        log.info("images.header_not_found", q=header_kw)

    # 본문 마커 이미지 (0~3장)
    markers = extract_markers(article.body_markdown)
    log.info("images.markers_found", n=len(markers))
    body_images = fetch_for_markers(markers, limit=3)
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
