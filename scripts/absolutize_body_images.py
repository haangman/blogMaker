"""기존 글 본문 이미지 path 를 절대 URL 로 변환.

문제:
- 본문 마크다운 이미지가 `![alt]({{ site.baseurl }}/assets/img/.../slug-1.jpg)` 형태.
- chirpy(J-Blog-AI) 의 image 후처리가 markdown src 에 다시 baseurl 을 prepend 해서
  최종 HTML 이 `/J-Blog-AI/J-Blog-AI/assets/...` 로 깨진다 (404 — shimmer 박스만 보임).
- beautiful-jekyll(J-Blog), minimal-mistakes(J-Blog-Fashion) 는 baseurl 단일 적용
  으로 정상이지만, 모든 테마 통일을 위해 절대 URL 로 일괄 변환.

변환 패턴:
  `{{ site.baseurl }}/assets/img/...`  →  `https://haangman.github.io/<repo>/assets/img/...`

사용:
  python -m scripts.absolutize_body_images                  # 세 블로그 모두
  python -m scripts.absolutize_body_images --dry-run
  python -m scripts.absolutize_body_images --blog J-Blog-AI
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


SITE = "https://haangman.github.io"


@dataclass
class BlogTarget:
    repo_path: Path
    name: str
    repo_name: str


DEFAULT_BLOGS = [
    BlogTarget(Path(r"C:\Users\김은희\Downloads\J-Blog"),         "J-Blog",         "J-Blog"),
    BlogTarget(Path(r"C:\Users\김은희\Downloads\J-Blog-AI"),      "J-Blog-AI",      "J-Blog-AI"),
    BlogTarget(Path(r"C:\Users\김은희\Downloads\J-Blog-Fashion"), "J-Blog-Fashion", "J-Blog-Fashion"),
]


# `{{ site.baseurl }}/<path>` 또는 `{{site.baseurl}}/<path>` 둘 다 매칭
_BASEURL_LIQUID_RE = re.compile(r"\{\{\s*site\.baseurl\s*\}\}/")


def absolutize_post(path: Path, *, repo_name: str, dry_run: bool = False) -> int:
    """글 1편의 본문 안 `{{ site.baseurl }}/...` 를 절대 URL 로 치환. 치환 횟수 반환."""
    text = path.read_text(encoding="utf-8")
    # frontmatter 영역은 건드리지 않는다 — 본문 부분만 치환.
    # `---` 으로 시작·끝나는 frontmatter 를 분리.
    parts = text.split("---", 2)
    if len(parts) >= 3 and parts[0] == "":
        # 일반 형태: "" / frontmatter / body
        head = "---" + parts[1] + "---"
        body = parts[2]
    else:
        head = ""
        body = text

    replacement = f"{SITE}/{repo_name}/"
    new_body, n = _BASEURL_LIQUID_RE.subn(replacement, body)
    if n == 0:
        return 0

    if not dry_run:
        path.write_text(head + new_body, encoding="utf-8")
    return n


def process_blog(blog: BlogTarget, *, dry_run: bool) -> dict:
    posts_dir = blog.repo_path / "_posts"
    if not posts_dir.exists():
        return {"blog": blog.name, "skipped": "no _posts"}

    md_files = sorted(posts_dir.glob("*.md"))
    print(f"\n=== {blog.name} — {len(md_files)} posts ===")
    touched = 0
    total_subs = 0
    for p in md_files:
        try:
            n = absolutize_post(p, repo_name=blog.repo_name, dry_run=dry_run)
        except Exception as e:
            print(f"  [ERR] {p.name}: {e}", file=sys.stderr)
            continue
        if n:
            touched += 1
            total_subs += n
            print(f"  + {p.name}: {n} subs")
    print(f"  ({touched} posts touched, {total_subs} total substitutions)")
    return {"blog": blog.name, "touched": touched, "subs": total_subs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--blog", choices=[b.name for b in DEFAULT_BLOGS], default=None)
    args = parser.parse_args()

    blogs = DEFAULT_BLOGS if args.blog is None else [b for b in DEFAULT_BLOGS if b.name == args.blog]
    if args.dry_run:
        print("[INFO] DRY RUN — no files written")

    summary = []
    for blog in blogs:
        summary.append(process_blog(blog, dry_run=args.dry_run))

    print("\n=== SUMMARY ===")
    for s in summary:
        if "skipped" in s:
            print(f"  · {s['blog']}: skipped ({s['skipped']})")
        else:
            print(f"  · {s['blog']}: {s['touched']} posts, {s['subs']} substitutions")


if __name__ == "__main__":
    main()
