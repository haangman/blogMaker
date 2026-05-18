"""테마 전환 후 기존 글 본문 보정.

문제:
- minima 시절에 발행된 글들은 본문 첫 줄에 헤더 이미지를 마크다운 으로 삽입했다.
- 새 테마들 (beautiful-jekyll/chirpy/minimal-mistakes) 은 frontmatter 의
  cover-img / image / header.overlay_image 를 본문 위 hero 로 자동 렌더링한다.
- 그래서 같은 헤더 이미지가 **두 번** 보이는 글이 됨.

이 스크립트는 본문 시작부 가까이에 있는 헤더 이미지 (slug.jpg 와 일치하는 마크다운
이미지 + 그 다음 줄의 크레딧 라인) 를 한 번만 제거한다. 본문 중간의
[IMAGE: ...] 마커에서 치환된 슬러그-1.jpg, 슬러그-2.jpg 같은 본문 마커 이미지는
건드리지 않는다.

추가로 J-Blog-AI (chirpy) 글에서 본문에 ```mermaid 블록이 있으면 frontmatter
`mermaid: true` 를 추가한다 — chirpy 가 mermaid 를 활성화하는 데 필요한 키.

사용:
  python -m scripts.cleanup_post_bodies                  # 세 블로그 모두
  python -m scripts.cleanup_post_bodies --dry-run        # 미리보기
  python -m scripts.cleanup_post_bodies --blog J-Blog    # 한 블로그만
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

import frontmatter


@dataclass
class BlogTarget:
    repo_path: Path
    name: str
    theme: str   # beautiful-jekyll | chirpy | minimal-mistakes


DEFAULT_BLOGS = [
    BlogTarget(Path(r"C:\Users\김은희\Downloads\J-Blog"),         "J-Blog",         "beautiful-jekyll"),
    BlogTarget(Path(r"C:\Users\김은희\Downloads\J-Blog-AI"),      "J-Blog-AI",      "chirpy"),
    BlogTarget(Path(r"C:\Users\김은희\Downloads\J-Blog-Fashion"), "J-Blog-Fashion", "minimal-mistakes"),
]


# 본문에 헤더 마크다운 이미지가 들어간 패턴:
#   ![alt 텍스트]({{ site.baseurl }}/assets/img/YYYY/MM/<slug>.jpg)
#   *[Photo by ... ](url)*
#   (빈 줄)
# 슬러그 끝에 -1, -2 같은 인덱스가 붙은 것은 본문 마커이므로 제외.
_HEADER_IMG_RE = re.compile(
    r'!\[[^\]]*\]\(\{\{\s*site\.baseurl\s*\}\}/assets/img/\d{4}/\d{2}/(?P<base>[^/)]+?)\.(?:jpg|jpeg|png|webp|gif)\)\s*\n'
    r'(?:\*\[[^\]]*\]\([^\)]+\)\*\s*\n)?'
    r'\n*',
    flags=re.IGNORECASE,
)

_MERMAID_RE = re.compile(r"^```mermaid\b", flags=re.MULTILINE)


def _slug_from_filename(path: Path) -> str:
    # 2026-05-18-slug-abcd12.md → slug-abcd12
    name = path.stem
    # 첫 'YYYY-MM-DD-' 제거
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name)


def clean_post(path: Path, *, theme: str, dry_run: bool = False) -> dict:
    text = path.read_text(encoding="utf-8")
    post = frontmatter.loads(text)
    body = post.content
    changes: list[str] = []

    slug = _slug_from_filename(path)

    # 1) 본문 첫 부분의 헤더 이미지 제거.
    #    본문 시작 ~ 첫 2000자 사이의 첫 번째 매치만 — 그리고 base 가 slug 와 일치할 때만
    new_body = body
    m = _HEADER_IMG_RE.search(body[:3000])
    if m:
        base = m.group("base")
        # base 가 정확히 글 슬러그 (인덱스 없음) 일 때만 헤더로 간주.
        # base == "<slug>" 면 헤더. base == "<slug>-1" 같으면 본문 마커라 두기.
        if base == slug:
            start, end = m.span()
            new_body = body[:start] + body[end:]
            changes.append("strip_header_image")

    if new_body != body:
        post.content = new_body
        body = new_body

    # 2) chirpy 블로그에서 mermaid 블록 감지 → frontmatter mermaid: true
    if theme == "chirpy" and _MERMAID_RE.search(body):
        if not post.metadata.get("mermaid"):
            post.metadata["mermaid"] = True
            changes.append("add_mermaid")

    if not changes:
        return {"path": path.name, "changes": []}

    if not dry_run:
        path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return {"path": path.name, "changes": changes}


def process_blog(blog: BlogTarget, *, dry_run: bool) -> dict:
    posts_dir = blog.repo_path / "_posts"
    if not posts_dir.exists():
        return {"blog": blog.name, "skipped": "no _posts dir"}

    md_files = sorted(posts_dir.glob("*.md"))
    print(f"\n=== {blog.name} ({blog.theme}) — {len(md_files)} posts ===")
    touched = 0
    for p in md_files:
        try:
            result = clean_post(p, theme=blog.theme, dry_run=dry_run)
        except Exception as e:
            print(f"  [ERR] {p.name}: {e}", file=sys.stderr)
            continue
        if result["changes"]:
            touched += 1
            print(f"  + {result['path']}: {', '.join(result['changes'])}")
    print(f"  ({touched} touched)")
    return {"blog": blog.name, "touched": touched, "total": len(md_files)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--blog", choices=[b.name for b in DEFAULT_BLOGS], default=None,
                        help="한 블로그만 처리. 미지정 시 모든 블로그.")
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
            print(f"  · {s['blog']}: {s['touched']} / {s['total']} touched")


if __name__ == "__main__":
    main()
