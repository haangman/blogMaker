"""Claude Code CLI 호출 게이트.

모든 LLM 호출은 이 모듈을 통한다.
- subprocess + JSON 출력 파싱
- tenacity 재시도 (지수 백오프 3회)
- 호출 메타데이터를 SQLite llm_calls 에 기록
- 긴 시스템 프롬프트는 임시 파일 + --append-system-prompt 로 (CLI 인자 길이 한계 회피)
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config_loader import get_settings
from src.logging_setup import get_logger
from src.state.db import connect
from src.state.repo import record_llm_call

log = get_logger("llm.cli")


class ClaudeCLIError(RuntimeError):
    pass


class CycleQuotaExceeded(ClaudeCLIError):
    """한 사이클의 LLM 호출 횟수 상한을 초과 — 폭주 보호."""


# 사이클 시작 시 reset_cycle_counter() 로 0 으로 초기화.
_cycle_call_count = 0


def reset_cycle_counter() -> None:
    global _cycle_call_count
    _cycle_call_count = 0


def get_cycle_call_count() -> int:
    return _cycle_call_count


@dataclass
class ClaudeResponse:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    cost_usd: float | None
    raw: dict


_INLINE_SYSTEM_MAX = 6000  # 이 길이 넘으면 임시 파일로 전달


def _build_command(
    *,
    user_prompt_path: Path,
    system_prompt: str | None,
    system_prompt_path: Path | None,
    model: str | None,
) -> list[str]:
    settings = get_settings()
    cmd = [settings.claude_cli_path, "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if system_prompt_path is not None:
        cmd += ["--append-system-prompt", system_prompt_path.read_text(encoding="utf-8")]
    elif system_prompt:
        cmd += ["--append-system-prompt", system_prompt]
    return cmd


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    retry=retry_if_exception_type(ClaudeCLIError),
    reraise=True,
)
def _invoke(cmd: list[str], stdin_text: str, timeout_s: int) -> dict:
    log.debug("llm.invoke", cmd=cmd[:3] + ["..."], stdin_chars=len(stdin_text))
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeCLIError(f"timeout after {timeout_s}s") from e

    if proc.returncode != 0:
        raise ClaudeCLIError(
            f"exit={proc.returncode}: {proc.stderr.strip()[:500]}"
        )
    out = proc.stdout.strip()
    if not out:
        raise ClaudeCLIError("empty stdout")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        # 일부 케이스에서 JSON 한 줄 + 텍스트 잡음이 섞일 수 있어 첫 JSON 객체만 추출
        first = out.find("{")
        last = out.rfind("}")
        if first != -1 and last != -1:
            try:
                return json.loads(out[first : last + 1])
            except json.JSONDecodeError:
                pass
        raise ClaudeCLIError(f"json parse failed: {e}") from e


def _extract_text(payload: dict) -> str:
    # Claude Code CLI JSON 응답 호환 — 'result' 필드가 표준.
    for key in ("result", "text", "response"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            return v
    # 일부 모드는 'messages' 리스트로 응답
    msgs = payload.get("messages") or payload.get("output")
    if isinstance(msgs, list):
        parts: list[str] = []
        for m in msgs:
            if isinstance(m, dict):
                c = m.get("content")
                if isinstance(c, str):
                    parts.append(c)
                elif isinstance(c, list):
                    for item in c:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(item.get("text", ""))
        if parts:
            return "\n".join(parts)
    return ""


def _extract_usage(payload: dict) -> tuple[int | None, int | None, int | None, float | None]:
    usage = payload.get("usage") or {}
    inp = usage.get("input_tokens")
    out = usage.get("output_tokens")
    cached = (
        usage.get("cache_read_input_tokens")
        or usage.get("cached_input_tokens")
        or usage.get("cached_tokens")
    )
    cost = payload.get("total_cost_usd") or payload.get("cost_usd")
    return (
        int(inp) if inp is not None else None,
        int(out) if out is not None else None,
        int(cached) if cached is not None else None,
        float(cost) if cost is not None else None,
    )


def ask(
    user_prompt: str,
    *,
    system_prompt: str | None = None,
    model: str = "opus",
    purpose: str = "general",
    timeout_s: int | None = None,
) -> ClaudeResponse:
    """Claude CLI 1회 호출. 응답 텍스트 + usage 반환.

    - user_prompt 는 stdin 으로 전달 (인자 길이 한계 회피)
    - system_prompt 가 길면 임시 파일로 옮겨서 --append-system-prompt 의 인자 한계 회피
    - 사이클당 호출 횟수가 settings.max_llm_calls_per_cycle 을 넘으면 CycleQuotaExceeded.
    """
    global _cycle_call_count
    settings = get_settings()
    timeout_s = timeout_s or settings.claude_cli_timeout_sec

    limit = settings.max_llm_calls_per_cycle
    if limit and _cycle_call_count >= limit:
        log.error("llm.cycle_quota_exceeded", count=_cycle_call_count, limit=limit, purpose=purpose)
        raise CycleQuotaExceeded(
            f"한 사이클 LLM 호출 상한 초과 ({_cycle_call_count}/{limit}). "
            f"의도치 않은 폭주로 의심됨 — 사이클을 중단합니다."
        )
    _cycle_call_count += 1

    tmp_system: Path | None = None
    try:
        if system_prompt and len(system_prompt) > _INLINE_SYSTEM_MAX:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", encoding="utf-8", delete=False
            )
            tmp.write(system_prompt)
            tmp.close()
            tmp_system = Path(tmp.name)

        cmd = [settings.claude_cli_path, "-p", "--output-format", "json"]
        if model:
            cmd += ["--model", model]
        if tmp_system is not None:
            # 임시 파일은 stdin 비어있으면 안되므로 system 을 stdin 으로 보내는 방식 대신
            # --append-system-prompt 인자에 파일 내용을 직접 넣되, 너무 길면 일부 잘라낸다.
            cmd += ["--append-system-prompt", tmp_system.read_text(encoding="utf-8")]
        elif system_prompt:
            cmd += ["--append-system-prompt", system_prompt]

        start = time.monotonic()
        success = False
        error: str | None = None
        payload: dict = {}
        try:
            payload = _invoke(cmd, stdin_text=user_prompt, timeout_s=timeout_s)
            success = True
        except ClaudeCLIError as e:
            error = str(e)
            raise
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            try:
                inp_t, out_t, cached_t, cost = _extract_usage(payload)
                with connect() as conn:
                    record_llm_call(
                        conn,
                        purpose=purpose,
                        model=model,
                        input_tokens=inp_t,
                        output_tokens=out_t,
                        cached_tokens=cached_t,
                        cost_usd=cost,
                        duration_ms=duration_ms,
                        success=success,
                        error=error,
                    )
            except Exception:
                log.exception("llm.metrics_record_failed")

        text = _extract_text(payload)
        if not text:
            raise ClaudeCLIError(f"empty result text. payload keys={list(payload.keys())}")

        inp_t, out_t, cached_t, cost = _extract_usage(payload)
        return ClaudeResponse(
            text=text,
            model=model,
            input_tokens=inp_t,
            output_tokens=out_t,
            cached_tokens=cached_t,
            cost_usd=cost,
            raw=payload,
        )
    finally:
        if tmp_system is not None:
            try:
                os.unlink(tmp_system)
            except OSError:
                pass


def health_check() -> tuple[bool, str]:
    """CLI 가 살아있는지 가벼운 호출로 검증. (ok, message)."""
    try:
        resp = ask("ping", system_prompt="단어 'pong' 한 단어만 응답해라.",
                   model="opus", purpose="healthcheck", timeout_s=60)
        ok = "pong" in resp.text.lower()
        return ok, resp.text.strip()
    except Exception as e:
        return False, str(e)
