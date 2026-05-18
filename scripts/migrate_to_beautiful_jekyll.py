"""J-Blog 기존 _posts/*.md 의 frontmatter 를 beautiful-jekyll 호환으로 마이그레이션.

V7-B-2: minima → beautiful-jekyll 전환에 따른 일회성 스크립트.

변경 내용 (글 1편당):
- `image: <url>` 가 있으면 → `cover-img`, `thumbnail-img`, `share-img` 추가 (image 도 그대로 유지)
- `category: <id>` 단일 → `categories: [<id>]` 도 추가 (category 는 그대로 유지)
- summary 가 있으면 → `subtitle: <summary 앞 120자>` 추가

사용: python -m scripts.migrate_to_beautiful_jekyll [--blog-root <path>] [--dry-run]
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

# Windows cp949 콘솔에서 유니코드 출력
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import frontmatter


DEFAULT_BLOG_ROOT = Path(r"C:\Users\김은희\Downloads\J-Blog")


def migrate_post(path: Path, *, dry_run: bool = False) -> dict:
    post = frontmatter.load(str(path))
    fm = post.metadata
    changes: list[str] = []

    # 1) image → cover-img / thumbnail-img / share-img
    img = fm.get("image")
    if isinstance(img, str) and img.strip():
        if not fm.get("cover-img"):
            fm["cover-img"] = img
            changes.append("cover-img")
        if not fm.get("thumbnail-img"):
            fm["thumbnail-img"] = img
            changes.append("thumbnail-img")
        if not fm.get("share-img"):
            fm["share-img"] = img
            changes.append("share-img")

    # 2) category → categories
    cat = fm.get("category")
    if isinstance(cat, str) and cat and not fm.get("categories"):
        fm["categories"] = [cat]
        changes.append("categories")

    # 3) summary → subtitle
    summary = fm.get("summary") or fm.get("description")
    if isinstance(summary, str) and summary.strip() and not fm.get("subtitle"):
        fm["subtitle"] = summary[:120].strip()
        changes.append("subtitle")

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
