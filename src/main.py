"""한 사이클 엔트리포인트. Windows Task Scheduler가 이 모듈을 호출.

V4 흐름:
  phase 0(부팅 + 잠금 + DB 마이그레이션 + LLM 카운터 리셋)
  → enabled 블로그 각각:
      phase 1(수집, blog.sources_file)
      phase 2(정규화)
      phase 3(클러스터링, LLM 없이)
      phase 5(N개 선정)
      각 후보마다:
        phase 4(enrich, blog.categories_file)
        phase 6(write, blog.persona_files / mermaid 안내)
        phase 7(images)
        phase 8(gate + rewrite loop)
        phase 9(publish, blog.repo_path)
      phase 10(정리)
"""

from __future__ import annotations

import json
import sys

from src.backlog import mark_published, pick_backlog_topics
from src.backlog.loader import BacklogTopic
from src.blogs import BlogProfile, enabled_blogs
from src.cluster.merge import TopicCluster, cluster_only, enrich_with_llm
from src.cluster.simhash import hamming, simhash64, to_signed64
from src.collectors.registry import load_active_collectors
from src.config_loader import DATA_DIR, get_settings
from src.images import attach_images
from src.llm import (
    CycleQuotaExceeded,
    get_cycle_call_count,
    health_check,
    reset_cycle_counter,
    set_current_blog,
)
from src.logging_setup import get_logger, setup_logging
from src.normalize import normalize_batch
from src.publisher import publish
from src.selector.followup import encode_embedding, find_followup
from src.selector.score import IN_CYCLE_SIMHASH_GAP, is_recent_duplicate, pick_topics
from src.state.db import connect, migrate
from src.state.repo import record_published, record_source_failure, record_source_success
from src.utils.lockfile import LockBusy, cycle_lock
from src.utils.timeutil import iso_now, now_seoul
from src.writer.generator import write_article


def _save_trends_dump(items: list, suffix: str = "") -> None:
    dump_dir = DATA_DIR / "trends"
    dump_dir.mkdir(parents=True, exist_ok=True)
    fname = now_seoul().strftime("%Y-%m-%d-%H%M") + (f"-{suffix}" if suffix else "") + ".json"
    payload = [
        {
            "source_id": it.source_id,
            "external_id": it.external_id,
            "url": it.url,
            "title": it.title,
            "body": (it.body or "")[:2000],
            "lang": it.lang,
            "published_at": it.published_at.isoformat() if it.published_at else None,
            "extra": it.extra,
        }
        for it in items
    ]
    (dump_dir / fname).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _publish_one(
    candidate,
    *,
    log,
    blog: BlogProfile,
    in_cycle_simhashes: list[int],
    settings,
) -> bool:
    candidate = enrich_with_llm(candidate, categories_file=blog.categories_file)

    if is_recent_duplicate(candidate.simhash,
                            days=settings.duplicate_window_days,
                            blog_id=blog.id):
        log.info("article.skip_dup_after_enrich",
                 title=candidate.event_title, simhash=candidate.simhash, blog=blog.id)
        return False
    if any(hamming(candidate.simhash, h) <= IN_CYCLE_SIMHASH_GAP for h in in_cycle_simhashes):
        log.info("article.skip_in_cycle_dup",
                 title=candidate.event_title, simhash=candidate.simhash, blog=blog.id)
        return False

    log.info("article.enriched",
             title=candidate.event_title, category=candidate.category,
             simhash=candidate.simhash, blog=blog.id)

    followup = find_followup(candidate)
    if followup:
        log.info("article.followup_attached",
                 prev=followup.previous_title, cosine=followup.cosine, blog=blog.id)

    article, gate = write_article(candidate, followup=followup, blog=blog)
    if gate.outcome != "pass":
        log.warning("article.gate_failed", title=candidate.event_title,
                    failures=gate.failures, score=gate.score, blog=blog.id)
        return False

    if followup and followup.previous_url:
        article.updates_url = followup.previous_url

    attach_images(article, candidate)

    info = publish(article, blog=blog)
    log.info("article.published", path=str(info.post_path),
             pushed=info.pushed, sha=info.commit_sha, blog=blog.id)

    with connect() as conn:
        record_published(
            conn,
            cluster_simhash=candidate.simhash,
            title=article.title,
            category=article.category,
            post_path=str(info.post_path),
            source_urls=[s.url for s in article.sources],
            cluster_embedding=encode_embedding(candidate.embedding)
                if candidate.embedding is not None else None,
            blog_id=blog.id,
        )
    in_cycle_simhashes.append(candidate.simhash)
    return True


def run_for_blog(blog: BlogProfile) -> int:
    log = get_logger("main")
    settings = get_settings()
    set_current_blog(blog.id)
    log.info("blog.start", blog=blog.id, name=blog.name,
             repo=blog.repo_name, articles_per_cycle=blog.articles_per_cycle)

    # phase 1: collect
    collectors = load_active_collectors(blog.sources_file)
    log.info("blog.collectors", n=len(collectors), blog=blog.id)
    raws = []
    for c in collectors:
        try:
            fetched = c.fetch()
            raws.extend(fetched)
            with connect() as conn:
                record_source_success(conn, c.source_id)
        except Exception as e:
            log.warning("collector.failed", source=c.source_id, error=str(e), blog=blog.id)
            try:
                with connect() as conn:
                    record_source_failure(conn, c.source_id, str(e)[:500])
            except Exception:
                log.exception("collector.health_record_failed")
    log.info("blog.collected", total=len(raws), blog=blog.id)
    if not raws:
        log.info("blog.empty_collect", blog=blog.id)
        return 0

    # phase 2: normalize
    items = normalize_batch(raws, fetch_body=False)
    log.info("blog.normalized", n=len(items), blog=blog.id)
    _save_trends_dump(items, suffix=blog.id)

    # phase 3: cluster
    clusters = cluster_only(items)
    log.info("blog.clusters", n=len(clusters), blog=blog.id)
    if not clusters:
        log.info("blog.no_clusters", blog=blog.id)
        return 0

    # phase 5: select N
    candidates = pick_topics(
        clusters,
        n=blog.articles_per_cycle,
        selector_profile=blog.selector_profile,
        blog_id=blog.id,
    )
    log.info("blog.candidates", n=len(candidates), blog=blog.id)
    if not candidates:
        log.info("blog.nothing_to_publish", blog=blog.id)
        return 0

    in_cycle_simhashes: list[int] = []
    published_count = 0
    for idx, candidate in enumerate(candidates, 1):
        try:
            ok = _publish_one(
                candidate, log=log, blog=blog,
                in_cycle_simhashes=in_cycle_simhashes, settings=settings,
            )
            if ok:
                published_count += 1
        except CycleQuotaExceeded:
            log.error("cycle.quota_exceeded_midway",
                      published=published_count, blog=blog.id,
                      llm_calls=get_cycle_call_count())
            raise
        except Exception:
            log.exception("article.unhandled", idx=idx, blog=blog.id,
                          title=getattr(candidate, "event_title", "?"))
            continue

    # V4-8: backlog 보충 — 트렌드만으로 부족하면 backlog 에서 채움
    if blog.backlog_file:
        remaining = blog.articles_per_cycle - published_count
        # backlog_ratio 가 설정돼 있으면 그 비율도 추가 (트렌드와 함께 발행)
        target_backlog_n = max(remaining, int(blog.articles_per_cycle * blog.backlog_ratio))
        target_backlog_n = min(target_backlog_n, blog.articles_per_cycle - published_count)
        if target_backlog_n > 0:
            backlog_topics = pick_backlog_topics(
                blog.id, n=target_backlog_n,
                cycle_simhashes=in_cycle_simhashes,
            )
            log.info("blog.backlog_picked", blog=blog.id, n=len(backlog_topics))
            for topic in backlog_topics:
                try:
                    ok = _publish_backlog_one(
                        topic, log=log, blog=blog,
                        in_cycle_simhashes=in_cycle_simhashes, settings=settings,
                    )
                    if ok:
                        published_count += 1
                except CycleQuotaExceeded:
                    log.error("cycle.quota_exceeded_midway_backlog",
                              published=published_count, blog=blog.id)
                    raise
                except Exception:
                    log.exception("backlog.article_unhandled",
                                  topic_id=topic.id, blog=blog.id)
                    continue

    log.info("blog.end", blog=blog.id, published=published_count,
             attempted=len(candidates), llm_calls=get_cycle_call_count())
    return published_count


def _publish_backlog_one(
    topic: BacklogTopic,
    *,
    log,
    blog: BlogProfile,
    in_cycle_simhashes: list[int],
    settings,
) -> bool:
    """백로그 토픽 1개를 글로 작성 후 발행."""
    # 가짜 TopicCluster — items=[], category/title/summary 는 backlog 항목에서
    fake = TopicCluster(
        items=[],
        event_title=topic.topic,
        event_summary=(
            f"AI 카테고리 '{topic.category}' 의 {topic.depth} 수준 핵심 토픽 정리. "
            f"독자가 처음 접해도 따라올 수 있게 비유·예시·필요 시 다이어그램·코드 스니펫 포함."
        ),
        category=topic.category,
        simhash=topic.topic_simhash or to_signed64(simhash64(topic.topic)),
        embedding=None,
        enriched=True,
    )

    if any(hamming(fake.simhash, h) <= IN_CYCLE_SIMHASH_GAP for h in in_cycle_simhashes):
        log.info("backlog.skip_in_cycle_dup", topic_id=topic.id, topic=topic.topic)
        return False

    log.info("backlog.writing", topic_id=topic.id, topic=topic.topic,
             category=topic.category, depth=topic.depth, blog=blog.id)

    article, gate = write_article(fake, followup=None, blog=blog)
    if gate.outcome != "pass":
        log.warning("backlog.gate_failed", topic=topic.topic,
                    failures=gate.failures, score=gate.score, blog=blog.id)
        return False

    attach_images(article, fake)

    info = publish(article, blog=blog)
    log.info("backlog.published", path=str(info.post_path), pushed=info.pushed,
             topic_id=topic.id, blog=blog.id)

    with connect() as conn:
        record_published(
            conn,
            cluster_simhash=fake.simhash,
            title=article.title,
            category=article.category,
            post_path=str(info.post_path),
            source_urls=[],
            cluster_embedding=None,
            blog_id=blog.id,
        )
    mark_published(topic.id, str(info.post_path))
    in_cycle_simhashes.append(fake.simhash)
    return True


def run_cycle(blog_ids: list[str] | None = None) -> int:
    setup_logging()
    log = get_logger("main")
    settings = get_settings()

    try:
        with cycle_lock():
            log.info("cycle.start", dry_run=settings.dry_run, ts=iso_now())
            migrate()
            reset_cycle_counter()

            # 부팅 헬스체크 — Claude CLI 세션이 살아있는지. 만료면 사이클 abort.
            ok, msg = health_check()
            if not ok:
                log.error("cycle.health_check_failed", msg=msg)
                return 0
            log.info("cycle.health_check_ok")

            blogs = enabled_blogs()
            if blog_ids:
                blogs = [b for b in blogs if b.id in blog_ids]
            log.info("cycle.blogs", ids=[b.id for b in blogs])

            total_published = 0
            for blog in blogs:
                try:
                    total_published += run_for_blog(blog)
                except CycleQuotaExceeded as e:
                    log.error("cycle.quota_stop", reason=str(e),
                              published_so_far=total_published)
                    break
                except Exception:
                    log.exception("blog.unhandled", blog=blog.id)
                    continue

            log.info("cycle.end", status="ok",
                     total_published=total_published,
                     llm_calls=get_cycle_call_count())
            return 0
    except LockBusy as e:
        log.warning("cycle.lock_busy", reason=str(e))
        return 0
    except Exception:
        log.exception("cycle.unhandled_error", llm_calls=get_cycle_call_count())
        return 1


if __name__ == "__main__":
    sys.exit(run_cycle())
