"""사이클 결과 요약 — LLM 비용, 발행 이력, 게이트 점수."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "state.sqlite"


def main() -> None:
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row

    print("--- LLM 호출 ---")
    total = 0.0
    for r in c.execute(
        "SELECT purpose, model, input_tokens, output_tokens, cached_tokens, "
        "cost_usd, duration_ms, success FROM llm_calls ORDER BY at"
    ):
        cost = r["cost_usd"] or 0.0
        total += cost
        print(
            f"  {r['purpose']:25} {r['model'] or '-':8}"
            f"  in={r['input_tokens']} out={r['output_tokens']} cached={r['cached_tokens']}"
            f"  cost=${cost:.4f}  {r['duration_ms']}ms  ok={bool(r['success'])}"
        )
    print(f"  TOTAL cost: ${total:.4f}")

    print()
    print("--- 발행 이력 ---")
    for r in c.execute(
        "SELECT title, category, post_path, published_at FROM published ORDER BY id"
    ):
        print(f"  {r['published_at']}  [{r['category']}]  {r['title']}")

    print()
    print("--- 게이트 시도 ---")
    for r in c.execute(
        "SELECT attempt_num, gate_score, outcome, gate_failures "
        "FROM article_attempts ORDER BY id"
    ):
        print(
            f"  attempt={r['attempt_num']}  score={r['gate_score']}  "
            f"outcome={r['outcome']}  failures={r['gate_failures']}"
        )

    print()
    print("--- 소스 헬스 ---")
    for r in c.execute(
        "SELECT source_id, consec_failures, last_success_at, disabled "
        "FROM source_health ORDER BY source_id"
    ):
        print(
            f"  {r['source_id']:20}  fails={r['consec_failures']}  "
            f"last_ok={r['last_success_at']}  disabled={r['disabled']}"
        )


if __name__ == "__main__":
    main()
