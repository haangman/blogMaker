"""사이클 중복 실행 방지용 잠금 파일.

Task Scheduler가 이전 사이클이 끝나기 전에 두 번째 인스턴스를 띄워도
두 번째는 즉시 정상 종료한다.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from src.config_loader import DATA_DIR

LOCK_PATH = DATA_DIR / ".cycle.lock"


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if handle == 0:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        else:
            os.kill(pid, 0)
            return True
    except (OSError, PermissionError):
        return False


class LockBusy(RuntimeError):
    pass


@contextmanager
def cycle_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            prev_pid = int(LOCK_PATH.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            prev_pid = 0
        if prev_pid and _is_pid_alive(prev_pid):
            raise LockBusy(f"이전 사이클이 아직 동작 중 (pid={prev_pid})")
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass
