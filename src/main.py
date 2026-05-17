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

from src.blogs import BlogProfile, enabled_blogs
from src.cluster.merge import cluster_only, enrich_with_llm
from src.cluster.simhash import hamming
from src.collectors.registry import load_active_collectors
from src.config_loader import DATA_DIR, get_settings
from src.images import attach_images
from src.llm import CycleQuotaExceeded, get_cycle_call_count, reset_cycle_counter
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

    if is_recent_duplicate(candidate.simhash, days=settings.duplicate_window_days):
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

    # TODO V4-8: backlog 보충 — 트렌드 published_count < articles_per_cycle 면 backlog 에서 채움
    log.info("blog.end", blog=blog.id, published=published_count,
             attempted=len(candidates), llm_calls=get_cycle_call_count())
    return published_count


def run_cycle(blog_ids: list[str] | None = None) -> int:
    setup_logging()
    log = get_logger("main")
    settings = get_settings()

    try:
        with cycle_lock():
            log.info("cycle.start", dry_run=settings.dry_run, ts=iso_now())
            migrate()
            reset_cycle_counter()

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
