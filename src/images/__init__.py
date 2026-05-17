"""클러스터 키워드로 영문 이미지 검색어를 만들고, Unsplash → Pexels 순으로 시도."""

from __future__ import annotations

from src.cluster.merge import TopicCluster
from src.images import pexels, unsplash
from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger
from src.publisher.models import ArticleDraft

log = get_logger("images")


_KEYWORD_SYSTEM = (
    "사건 요약을 받아서 이미지 스톡 사이트(Unsplash) 검색용 영문 키워드 2~3 단어를 "
    "한 줄로만 답한다. 다른 설명 금지. 예: 'remote work laptop' 같은 식."
)


def _image_keywords(cluster: TopicCluster) -> str:
    user = f"제목: {cluster.event_title}\n요약: {cluster.event_summary}"
    try:
        resp = ask(user, system_prompt=_KEYWORD_SYSTEM, model="haiku",
                   purpose="image_keywords", timeout_s=60)
        kw = resp.text.strip().splitlines()[0].strip()
        return kw or cluster.category
    except ClaudeCLIError:
        return cluster.category


def attach_image(article: ArticleDraft, cluster: TopicCluster) -> None:
    """글 draft 에 이미지를 첨부 (없으면 그냥 지나감)."""
    if not article.body_markdown:
        return
    query = _image_keywords(cluster)
    log.info("images.query", q=query)

    result = unsplash.search_and_download(query) or pexels.search_and_download(query)
    if not result:
        log.info("images.none_found", q=query)
        return

    local_path, meta = result
    article.image_local_path = local_path
    article.image_alt = meta.get("alt") or query
    credit = meta.get("credit") or ""
    credit_url = meta.get("credit_url") or ""
    article.image_credit = f"[{credit}]({credit_url})" if credit_url else credit
    log.info("images.attached", local=str(local_path), credit=article.image_credit)
