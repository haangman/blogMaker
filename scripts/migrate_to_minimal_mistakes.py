"""J-Blog-Fashion 기존 _posts/*.md frontmatter 를 minimal-mistakes 호환으로 마이그레이션.

V8-B: minima → minimal-mistakes 전환에 따른 일회성 스크립트.

변경 내용 (글 1편당):
- `image: <url>` 가 있으면 → `header.teaser` + `header.overlay_image` + `header.overlay_filter` 추가
- `category: <id>` 단일 → `categories: [<id>]` 도 추가
- summary 가 있으면 → `excerpt: <summary 앞 160자>` 추가
- `layout: post` → `layout: single` (minimal-mistakes 기본 글 레이아웃)

사용: python -m scripts.migrate_to_minimal_mistakes [--blog-root <path>] [--dry-run]
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import frontmatter


DEFAULT_BLOG_ROOT = Path(r"C:\Users\김은희\Downloads\J-Blog-Fashion")


def migrate_post(path: Path, *, dry_run: bool = False) -> dict:
    post = frontmatter.load(str(path))
    fm = post.metadata
    changes: list[str] = []

    # 1) layout: post → single
    if fm.get("layout") == "post":
        fm["layout"] = "single"
        changes.append("layout")

    # 2) image → header.teaser + header.overlay_image
    img = fm.get("image")
    if isinstance(img, str) and img.strip() and not fm.get("header"):
        fm["header"] = {
            "teaser": img,
            "overlay_image": img,
            "overlay_filter": 0.35,
        }
        changes.append("header")

    # 3) category → categories
    cat = fm.get("category")
    if isinstance(cat, str) and cat and not fm.get("categories"):
        fm["categories"] = [cat]
        changes.append("categories")

    # 4) summary → excerpt
    summary = fm.get("summary") or fm.get("description")
    if isinstance(summary, str) and summary.strip() and not fm.get("excerpt"):
        fm["excerpt"] = summary[:160].strip()
        changes.append("excerpt")

    if not changes:
        return {"path": str(path.name), "changes": []}

    if not dry_run:
        path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return {"path": str(path.name), "changes": changes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog-root", type=Path, default=DEFAULT_BLOG_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    posts_dir = args.blog_root / "_posts"
    if not posts_dir.exists():
        print(f"[ERR] _posts dir not found: {posts_dir}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(posts_dir.glob("*.md"))
    print(f"[INFO] {len(md_files)} posts in {posts_dir}")
    if args.dry_run:
        print("[INFO] DRY RUN — no files written\n")

    touched = 0
    for p in md_files:
        try:
            result = migrate_post(p, dry_run=args.dry_run)
        except Exception as e:
            print(f"[ERR] {p.name}: {e}", file=sys.stderr)
            continue
        if result["changes"]:
            touched += 1
            print(f"  + {result['path']}: {', '.join(result['changes'])}")
        else:
            print(f"  · {result['path']}: (no change)")

    print(f"\n[DONE] migrated {touched} / {len(md_files)} posts")


if __name__ == "__main__":
    main()
