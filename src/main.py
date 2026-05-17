"""한 사이클 엔트리포인트. Windows Task Scheduler가 이 모듈을 호출.

현재는 Step 1 scaffold 단계 — phase 0(부팅·잠금) 만 구현. 이후 단계가
collectors / cluster / writer / publisher 를 단계별로 채운다.
"""

from __future__ import annotations

import sys

from src.config_loader import get_settings
from src.logging_setup import get_logger, setup_logging
from src.state.db import migrate
from src.utils.lockfile import LockBusy, cycle_lock


def run_cycle() -> int:
    setup_logging()
    log = get_logger("main")
    settings = get_settings()

    try:
        with cycle_lock():
            log.info("cycle.start", dry_run=settings.dry_run)
            migrate()

            # TODO Step 3+: collect
            # TODO Step 5: cluster + categorize + select
            # TODO Step 4: write
            # TODO Step 7: images
            # TODO Step 4/7: quality gate + rewrite loop
            # TODO Step 2/4: publish to J-Blog

            log.info("cycle.scaffold_only",
                     note="Step 1 단계 — phase 0 (부팅·잠금·DB) 만 동작.")
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
