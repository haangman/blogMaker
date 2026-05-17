"""한 사이클 엔트리포인트. Windows Task Scheduler가 이 모듈을 호출.

흐름: phase 0(부팅) → 1(수집) → 2(정규화) → 3(클러스터링) → 4(분류) →
      5(선정) → 6(글 생성) → 7(이미지) → 8(품질 게이트) → 9(발행) → 10(정리).
각 단계는 외부 IO 실패에도 사이클 자체가 죽지 않도록 graceful 처리한다.
"""

from __future__ import annotations

import json
import sys

from src.cluster.merge import cluster_and_merge
from src.collectors.registry import load_active_collectors
from src.config_loader import DATA_DIR, get_settings
from src.images import attach_image
from src.logging_setup import get_logger, setup_logging
from src.normalize import normalize_batch
from src.publisher import publish
from src.quality.gate import GateResult, evaluate
from src.selector.followup import encode_embedding, find_followup
from src.selector.score import pick_topic
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


def run_cycle() -> int:
    setup_logging()
    log = get_logger("main")
    settings = get_settings()

    try:
        with cycle_lock():
            log.info("cycle.start", dry_run=settings.dry_run, ts=iso_now())
            migrate()

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

            # phase 3+4: cluster + merge + categorize
            clusters = cluster_and_merge(items)
            log.info("cycle.clusters", n=len(clusters))
            if not clusters:
                log.info("cycle.no_clusters")
                return 0

            # phase 5: select
            selected = pick_topic(clusters)
            if not selected:
                log.info("cycle.nothing_to_publish")
                return 0
            log.info("cycle.selected", title=selected.event_title, category=selected.category)

            # follow-up 모드 — 8~30일 내 비슷한 사건 있으면 컨텍스트 첨부
            followup = find_followup(selected)
            if followup:
                log.info("cycle.followup", prev=followup.previous_title, cosine=followup.cosine)

            # phase 6+8: write + gate + rewrite loop
            article, gate = write_article(selected, followup=followup)
            if gate.outcome != "pass":
                log.warning("cycle.gate_failed_terminal",
                            failures=gate.failures, score=gate.score)
                return 0

            if followup and followup.previous_url:
                article.updates_url = followup.previous_url

            # phase 7: image
            attach_image(article, selected)

            # phase 9: publish
            info = publish(article)
            log.info("cycle.published", path=str(info.post_path), pushed=info.pushed)

            with connect() as conn:
                record_published(
                    conn,
                    cluster_simhash=selected.simhash,
                    title=article.title,
                    category=article.category,
                    post_path=str(info.post_path),
                    source_urls=[s.url for s in article.sources],
                    cluster_embedding=encode_embedding(selected.embedding)
                        if selected.embedding is not None else None,
                )

            log.info("cycle.end", status="ok")
            return 0
    except LockBusy as e:
        log.warning("cycle.lock_busy", reason=str(e))
        return 0
    except Exception:
        log.exception("cycle.unhandled_error")
        return 1


if __name__ == "__main__":
    sys.exit(run_cycle())
