"""V2 변경 후 핵심 import + 함수 동작 smoke test."""

from src.images.markers import extract_markers, remove_marker_lines
from src.main import run_cycle  # noqa: F401
from src.publisher import ArticleDraft, ImageRef, SourceRef, publish  # noqa: F401
from src.quality.gate import evaluate


def main() -> None:
    body = (
        "어제 본 장면이 좀 묘하다. 사실은 이게 좀 웃긴 게, "
        "같은 화면에 정반대 흐름이 같이 있었다.\n\n"
        '[IMAGE: "korean office night"]\n\n'
        "그래서 한 발 떨어져서 본다. 평소엔 잘 안 보던 흐름이 "
        "오늘은 좀 더 또렷이 들어왔다.\n\n"
        "근데 그게 의미가 있을지는 또 다른 얘기다."
    ) * 3

    r = evaluate(body)
    print("gate.outcome:", r.outcome)
    print("gate.failures:", r.failures)
    print("gate.warnings:", r.warnings)

    print()
    print("extract_markers:", extract_markers(body))

    cleaned = remove_marker_lines(body)
    print()
    print("after remove_marker_lines body has marker?",
          '[IMAGE:' in cleaned)


if __name__ == "__main__":
    main()
