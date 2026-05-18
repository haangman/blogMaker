"""J-Blog-AI 의 기존 글 frontmatter 를 chirpy 호환 형태로 변환.

변환:
- category: tech → categories: [tech]   (chirpy 의 jekyll-archives 가 사용)
- image: <url string> → image: {path: <url>, alt: <title>}   (chirpy 글 헤더 형식)

기존 키 그대로 보존되는 것:
- title, date, tags, summary, description, slug, sources, updates_url, category_ko
"""

from __future__ import annotations

import sys
from pathlib import Path

import frontmatter

POSTS = Path("C:/Users/김은희/Downloads/J-Blog-AI/_posts")


def migrate_one(post_path: Path) -> dict:
    text = post_path.read_text(encoding="utf-8")
    post = frontmatter.loads(text)
    meta = dict(post.metadata)
    changes: list[str] = []

    # category → categories
    if "category" in meta:
        cat = meta.pop("category")
        if cat:
            if "categories" not in meta:
                meta["categories"] = [cat]
                changes.append(f"category→categories=[{cat}]")
            else:
                changes.append("category removed (categories already set)")

    # image: url → image: {path, alt}
    img = meta.get("image")
    if isinstance(img, str) and img:
        meta["image"] = {"path": img, "alt": meta.get("title", "image")}
        changes.append("image→{path,alt}")

    if changes:
        new_post = frontmatter.Post(content=post.content, **meta)
        post_path.write_text(frontmatter.dumps(new_post), encoding="utf-8")

    return {"name": post_path.name, "changes": changes}


def main() -> None:
    results = []
    for post in sorted(POSTS.glob("*.md")):
        r = migrate_one(post)
        results.append(r)
        if r["changes"]:
            print(f"  [MIG] {r['name']}: {', '.join(r['changes'])}")

    changed = [r for r in results if r["changes"]]
    print(f"\n총 {len(changed)}/{len(results)} 편 변환됨")


if __name__ == "__main__":
    main()
