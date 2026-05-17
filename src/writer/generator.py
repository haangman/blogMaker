"""클러스터 → 글 생성 + 게이트 + 재작성 루프."""

from __future__ import annotations

from src.cluster.merge import TopicCluster
from src.config_loader import DATA_DIR, load_quality_rules
from src.llm import ClaudeCLIError, ask
from src.logging_setup import get_logger
from src.publisher.models import ArticleDraft, SourceRef
from src.quality.gate import GateResult, evaluate
from src.selector.followup import FollowupContext
from src.state.db import connect
from src.state.repo import record_attempt
from src.utils.timeutil import iso_now
from src.writer.postprocess import clean
from src.writer.prompts import build_system_prompt, build_user_prompt

log = get_logger("writer")


_SUSPICIOUS_TITLE_HINTS = (
    "본문", "작성합니다", "작성", "여기", "다음과", "아래", "시작합니다",
)


def _title_for_article(cluster: TopicCluster, body: str) -> str:
    """글의 본문 첫 줄/사건 제목으로 글 제목 결정.

    첫 줄이 메타 라벨로 의심되면 cluster.event_title 로 폴백.
    """
    first_line = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    if not first_line:
        return cluster.event_title
    if first_line.startswith(("#", ">", "*", "-", "[", "!")):
        return cluster.event_title
    if any(hint in first_line for hint in _SUSPICIOUS_TITLE_HINTS) and len(first_line) <= 30:
        return cluster.event_title
    if not 6 <= len(first_line) <= 80:
        return cluster.event_title
    # 첫 줄이 문장처럼 길고 끝에 마침표 — 본문 첫 문장일 가능성 높음
    if len(first_line) >= 35 and first_line.endswith(("다.", "다", ".", "?", "다더라")):
        return cluster.event_title
    return first_line.rstrip(".")


def write_article(
    cluster: TopicCluster,
    followup: FollowupContext | None = None,
) -> tuple[ArticleDraft, GateResult]:
    rules = load_quality_rules()
    max_rewrites = int((rules.get("rewrite") or {}).get("max_attempts", 2))

    feedback: list[str] = []
    last_body = ""
    last_gate: GateResult | None = None

    for attempt in range(1, max_rewrites + 2):
        system = build_system_prompt(rewrite_feedback=feedback if attempt > 1 else None)
        user = build_user_prompt(cluster, followup=followup)
        try:
            resp = ask(user, system_prompt=system, model="opus",
                       purpose=f"write_attempt_{attempt}")
        except ClaudeCLIError as e:
            log.warning("writer.llm_failed", attempt=attempt, error=str(e))
            with connect() as conn:
                record_attempt(
                    conn,
                    cluster_simhash=cluster.simhash,
                    attempt_num=attempt,
                    gate_score=None,
                    gate_failures=[f"llm_error: {e}"],
                    outcome="llm_error",
                )
            continue

        body = clean(resp.text)
        last_body = body
        gate = evaluate(body)
        last_gate = gate

        with connect() as conn:
            record_attempt(
                conn,
                cluster_simhash=cluster.simhash,
                attempt_num=attempt,
                gate_score=gate.score,
                gate_failures=gate.failures,
                outcome=gate.outcome,
            )

        log.info("writer.attempt", attempt=attempt,
                 outcome=gate.outcome, score=gate.score,
                 failures=gate.failures[:3])

        if gate.outcome == "pass":
            break
        feedback = gate.failures

    # 마지막 시도가 실패면 draft 보관 후 명확하게 fail 표시
    if not last_gate or last_gate.outcome != "pass":
        if last_body:
            dump = DATA_DIR / "drafts" / f"{iso_now().replace(':', '-')}.md"
            dump.parent.mkdir(parents=True, exist_ok=True)
            dump.write_text(last_body, encoding="utf-8")
            log.warning("writer.draft_saved", path=str(dump))
        gate_result = last_gate or GateResult(outcome="fail", score=0.0, failures=["no_output"])
        return _empty_draft(cluster), gate_result

    title = _title_for_article(cluster, last_body)
    sources = [SourceRef(url=it.url, title=it.title) for it in cluster.items[:5]]
    draft = ArticleDraft(
        title=title,
        body_markdown=last_body,
        category=cluster.category,
        summary=cluster.event_summary[:200],
        tags=[cluster.category],
        sources=sources,
        cluster_simhash=cluster.simhash,
    )
    if followup:
        draft.tags = list(set(draft.tags + ["follow-up"]))
    return draft, last_gate


def _empty_draft(cluster: TopicCluster) -> ArticleDraft:
    return ArticleDraft(
        title=cluster.event_title,
        body_markdown="",
        category=cluster.category,
        summary=cluster.event_summary[:200],
        tags=[cluster.category],
        sources=[],
        cluster_simhash=cluster.simhash,
    )
