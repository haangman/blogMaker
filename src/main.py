"""한 사이클 엔트리포인트. Windows Task Scheduler가 이 모듈을 호출.

V3 흐름: phase 0(부팅) → 1(수집) → 2(정규화) → 3(클러스터링) →
        5(선정 N개) → 각 후보마다 4(분류) → 6(글) → 7(이미지) → 8(게이트) → 9(발행)
        → 10(정리).
각 글은 독립적 — 한 편이 실패해도 다음 편은 계속.
"""

from __future__ import annotations

import json
import sys

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


def _publish_one(candidate, *, log, settings, in_cycle_simhashes: list[int]) -> bool:
    """후보 클러스터 1개를 enrich → 게이트 통과 시 발행. 성공이면 True."""
    candidate = enrich_with_llm(candidate)

    # enrich 후 정확한 simhash 로 다시 한 번 중복 검사 (이전 글 + in-cycle 양쪽)
    if is_recent_duplicate(candidate.simhash, days=settings.duplicate_window_days):
        log.info("article.skip_dup_after_enrich",
                 title=candidate.event_title, simhash=candidate.simhash)
        return False
    if any(hamming(candidate.simhash, h) <= IN_CYCLE_SIMHASH_GAP for h in in_cycle_simhashes):
        log.info("article.skip_in_cycle_dup",
                 title=candidate.event_title, simhash=candidate.simhash)
        return False

    log.info("article.enriched",
             title=candidate.event_title, category=candidate.category,
             simhash=candidate.simhash)

    followup = find_followup(candidate)
    if followup:
        log.info("article.followup_attached",
                 prev=followup.previous_title, cosine=followup.cosine)

    article, gate = write_article(candidate, followup=followup)
    if gate.outcome != "pass":
        log.warning("article.gate_failed", title=candidate.event_title,
                    failures=gate.failures, score=gate.score)
        return False

    if followup and followup.previous_url:
        article.updates_url = followup.previous_url

    attach_images(article, candidate)

    info = publish(article)
    log.info("article.published", path=str(info.post_path),
             pushed=info.pushed, sha=info.commit_sha)

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
        )
    in_cycle_simhashes.append(candidate.simhash)
    return True


def run_cycle() -> int:
    setup_logging()
    log = get_logger("main")
    settings = get_settings()

    try:
        with cycle_lock():
            log.info("cycle.start",
                     dry_run=settings.dry_run, ts=iso_now(),
                     articles_per_cycle=settings.articles_per_cycle,
                     duplicate_window_days=settings.duplicate_window_days)
            migrate()
            reset_cycle_counter()

            # phase 1: collect
            collectors = load_active_collectors()
            log.info("cycle.collectors", n=len(collectors))
            raws = []
            for c in collectors:
                try:
                    fetched = c.fetch()
                    raws.extend(fetched)
                    with connect() as conn:
                        record_source_success(conn, c.source_id)
                except Exception as e:
                    log.warning("collector.failed", source=c.source_id, error=str(e))
                    try:
                        with connect() as conn:
                            record_source_failure(conn, c.source_id, str(e)[:500])
                    except Exception:
                        log.exception("collector.health_record_failed")
            log.info("cycle.collected", total=len(raws))
            if not raws:
                log.info("cycle.empty_collect")
                return 0

            # phase 2: normalize
            items = normalize_batch(raws, fetch_body=False)
            log.info("cycle.normalized", n=len(items))
            _save_trends_dump(items)

            # phase 3: cluster (LLM 없이)
            clusters = cluster_only(items)
            log.info("cycle.clusters", n=len(clusters))
            if not clusters:
                log.info("cycle.no_clusters")
                return 0

            # phase 5: select N
            candidates = pick_topics(clusters, n=settings.articles_per_cycle)
            log.info("cycle.candidates", n=len(candidates))
            if not candidates:
                log.info("cycle.nothing_to_publish")
                return 0

            # phase 6~9: 후보 마다 enrich → write → gate → image → publish
            in_cycle_simhashes: list[int] = []
            published_count = 0
            for idx, candidate in enumerate(candidates, 1):
                try:
                    ok = _publish_one(
                        candidate,
                        log=log,
                        settings=settings,
                        in_cycle_simhashes=in_cycle_simhashes,
                    )
                    if ok:
                        published_count += 1
                except CycleQuotaExceeded:
                    log.error("cycle.quota_exceeded_midway",
                              published=published_count,
                              llm_calls=get_cycle_call_count())
                    raise
                except Exception:
                    log.exception("article.unhandled", idx=idx,
                                  title=getattr(candidate, "event_title", "?"))
                    continue

            log.info("cycle.end", status="ok",
                     published=published_count,
                     attempted=len(candidates),
                     llm_calls=get_cycle_call_count())
            return 0
    except LockBusy as e:
        log.warning("cycle.lock_busy", reason=str(e))
        return 0
    except CycleQuotaExceeded as e:
        log.error("cycle.quota_exceeded", reason=str(e),
                  llm_calls=get_cycle_call_count())
        return 0
    except Exception:
        log.exception("cycle.unhandled_error", llm_calls=get_cycle_call_count())
        return 1


if __name__ == "__main__":
    sys.exit(run_cycle())
