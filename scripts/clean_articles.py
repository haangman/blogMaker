"""기존 발행 글 일괄 스캔·치유.

세 가지 정리:
1. 본문 내 **같은 이미지 마크다운 중복** — 두 번째 이후 제거 (이미지 line + 크레딧 line + 따라오는 빈 줄까지)
2. **본문 주제와 무관한 참고 링크** — Claude(opus)로 무관 idx 식별 후 frontmatter.sources + 본문 참고 섹션 동기화
3. **빈 sources frontmatter 키** — sources 가 [] 면 키 자체 제거 + 본문 참고 섹션도 제거

각 블로그 리포에서 변경된 파일이 1편 이상이면 commit/push.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.llm import ClaudeCLIError, ask  # noqa: E402

BLOG_ROOTS = [
    REPO_ROOT.parent / "J-Blog",
    REPO_ROOT.parent / "J-Blog-AI",
]

# SEO: 기존 글에 image frontmatter 자동 backfill 할 때 사용
SITE_URL = "https://haangman.github.io"
BLOG_BASEURL = {
    "J-Blog": "/J-Blog",
    "J-Blog-AI": "/J-Blog-AI",
}


_IMG_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_CREDIT_LINE_RE = re.compile(r"^\s*\*\[?Photo by.*$|^\s*\*\[.*Photo by.*\]\(.*\).*\*\s*$")
_REFS_BLOCK_RE = re.compile(
    r"\n+\*\*\*\s*\n+\*\*참고\*\*\s*\n.*?(?=\n*\Z)",
    re.DOTALL,
)
_JSON_ARRAY_RE = re.compile(r"\[\s*[\d\s,]*\s*\]")


def dedupe_images(body: str) -> tuple[str, list[str]]:
    """본문 내 같은 이미지 마크다운 라인의 두 번째 이후 등장 제거.

    한 이미지의 본문 표현은 일반적으로 3줄:
        ![alt]({{ site.baseurl }}/path)
        *[Photo by X on Unsplash](...)*
        (빈 줄)

    중복 발견 시 이 세 줄 (또는 그 변형) 을 함께 제거.
    """
    seen: set[str] = set()
    removed_paths: list[str] = []
    lines = body.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _IMG_RE.match(line)
        if m:
            path = m.group(2).strip()
            if path in seen:
                removed_paths.append(path)
                # 이미지 line 자체 skip
                i += 1
                # 이어지는 크레딧 line(들) skip
                while i < len(lines) and _CREDIT_LINE_RE.match(lines[i]):
                    i += 1
                # 빈 줄 1~2개 정리 (앞 빈 줄도 정리)
                while i < len(lines) and not lines[i].strip():
                    i += 1
                # 결과 끝의 빈 줄 압축
                while out and not out[-1].strip():
                    out.pop()
                if out and out[-1].strip():
                    out.append("")
                continue
            seen.add(path)
        out.append(line)
        i += 1
    return "\n".join(out), removed_paths


_SYS_FILTER = (
    "한국어 블로그 글의 본문 주제와 명백히 무관한 '참고 링크' 의 인덱스를 식별한다.\n"
    "본문은 자연스러운 1인칭 글이고 참고 링크는 글 끝에 첨부된다.\n"
    "정확히 JSON 배열만 출력: [0, 2] 처럼 무관 idx. 무관이 없으면 [].\n"
    "보수적으로 — 약간이라도 관련 있으면 통과. 명백히 다른 주제(예: 증시 글에 정치 뉴스)만 골라낸다."
)


def filter_sources_by_llm(title: str, body: str, sources: list[dict]) -> tuple[list[dict], list[int]]:
    """본문 주제 외 source 를 LLM 으로 필터링."""
    if not sources or len(sources) < 2:
        return sources, []
    src_block = "\n".join(
        f"{i}. {s.get('title', '')[:120]} | {s.get('url', '')[:120]}"
        for i, s in enumerate(sources)
    )
    user = (
        f"글 제목: {title}\n\n"
        f"글 본문 (첫 1500 자):\n{body[:1500]}\n\n"
        f"참고 링크 목록:\n{src_block}"
    )
    try:
        resp = ask(user, system_prompt=_SYS_FILTER, model="opus", purpose="cleanup_source_filter")
    except ClaudeCLIError as e:
        print(f"  [warn] LLM source filter failed: {e}")
        return sources, []
    m = _JSON_ARRAY_RE.search(resp.text)
    if not m:
        return sources, []
    try:
        bad_idx = json.loads(m.group(0))
    except json.JSONDecodeError:
        return sources, []
    bad_set = {int(x) for x in bad_idx if isinstance(x, (int, float))}
    new_sources = [s for i, s in enumerate(sources) if i not in bad_set]
    return new_sources, sorted(bad_set)


def rewrite_references(body: str, sources: list[dict]) -> str:
    """본문 끝 참고 섹션을 새 sources 로 교체. 빈 sources 면 섹션 자체 제거."""
    cleaned = _REFS_BLOCK_RE.sub("", body).rstrip()
    if not sources:
        return cleaned
    parts = [cleaned, "", "***", "", "**참고**", ""]
    for s in sources:
        label = s.get("title") or s.get("url", "")
        parts.append(f"- [{label}]({s.get('url', '')})")
    return "\n".join(parts)


def _first_image_path(body: str) -> str | None:
    """본문 첫 번째 이미지의 경로 (앞 부분에 등장하는 것 — 헤더로 추정)."""
    for line in body.split("\n"):
        m = _IMG_RE.match(line)
        if m:
            return m.group(2).strip()
    return None


def clean_one(post_path: Path, blog_name: str = "") -> dict:
    text = post_path.read_text(encoding="utf-8")
    post = frontmatter.loads(text)
    body = post.content
    meta = dict(post.metadata)
    title = meta.get("title", "")

    info: dict = {
        "path": str(post_path),
        "name": post_path.name,
        "dedup_removed": 0,
        "src_removed_idx": [],
        "fm_sources_emptied": False,
        "image_added": False,
        "changed": False,
    }

    # 1. 이미지 dedupe
    new_body, dup_paths = dedupe_images(body)
    if dup_paths:
        info["dedup_removed"] = len(dup_paths)
        body = new_body

    # 2. sources LLM 필터
    sources = meta.get("sources") or []
    if isinstance(sources, list) and len(sources) >= 2:
        new_sources, bad_idx = filter_sources_by_llm(title, body, sources)
        if bad_idx:
            info["src_removed_idx"] = bad_idx
            meta["sources"] = new_sources
            body = rewrite_references(body, new_sources)

    # 3. 빈 sources frontmatter 키 제거
    if "sources" in meta and not meta["sources"]:
        del meta["sources"]
        info["fm_sources_emptied"] = True
        body = rewrite_references(body, [])

    # 4. SEO: image frontmatter backfill (헤더 이미지 절대 URL) + description
    if blog_name and blog_name in BLOG_BASEURL and "image" not in meta:
        first_img = _first_image_path(body)
        if first_img:
            # `{{ site.baseurl }}/path` → 절대 URL 로
            resolved = first_img.replace(
                "{{ site.baseurl }}", BLOG_BASEURL[blog_name]
            )
            if not resolved.startswith("http"):
                resolved = SITE_URL + (resolved if resolved.startswith("/") else "/" + resolved)
            meta["image"] = resolved
            info["image_added"] = True
    # jekyll-seo-tag 가 description 을 사용하므로 summary 와 동기화
    if "description" not in meta and meta.get("summary"):
        meta["description"] = meta["summary"]

    if (info["dedup_removed"] or info["src_removed_idx"]
            or info["fm_sources_emptied"] or info["image_added"]):
        info["changed"] = True
        new_post = frontmatter.Post(content=body, **meta)
        post_path.write_text(frontmatter.dumps(new_post), encoding="utf-8")
    return info


def git_commit_push(repo_root: Path, message: str) -> bool:
    """변경된 파일 있으면 commit/push. True if pushed."""
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(repo_root), capture_output=True, text=True
    )
    if not status.stdout.strip():
        return False
    subprocess.run(["git", "add", "-A"], cwd=str(repo_root), check=True)
    subprocess.run(
        [
            "git",
            "-c", "user.email=haangman@gmail.com",
            "-c", "user.name=haangman",
            "commit", "-m", message,
        ],
        cwd=str(repo_root),
        check=True,
    )
    subprocess.run(["git", "push"], cwd=str(repo_root), check=True)
    return True


def main() -> None:
    overall_changes: dict[str, list[dict]] = {}
    for blog_root in BLOG_ROOTS:
        posts_dir = blog_root / "_posts"
        if not posts_dir.exists():
            continue
        print(f"\n=== {blog_root.name} ===")
        changes: list[dict] = []
        for post in sorted(posts_dir.glob("*.md")):
            info = clean_one(post, blog_name=blog_root.name)
            if info["changed"]:
                changes.append(info)
                print(
                    f"  [CHANGED] {info['name']}  dedup={info['dedup_removed']}"
                    f"  src_removed={info['src_removed_idx']}"
                    f"  fm_empty={info['fm_sources_emptied']}"
                    f"  image_added={info['image_added']}"
                )
        if changes:
            overall_changes[blog_root.name] = changes
            msg_lines = [
                f"chore: 이미지 중복 / 무관 sources / 빈 frontmatter / SEO image 일괄 정리 ({len(changes)}편)",
                "",
                "blogMaker scripts/clean_articles.py 가 자동 검사.",
                "- 같은 이미지 마크다운이 두 번 이상 등장 → 두 번째 이후 제거 (크레딧 라인 포함)",
                "- LLM(opus) 으로 본문 주제와 무관한 참고 링크 식별 후 제거",
                "- 빈 sources frontmatter 키 제거 + 본문 끝 빈 참고 섹션 제거",
                "- SEO: 헤더 이미지 절대 URL 을 frontmatter image 키에 backfill",
                "  (jekyll-seo-tag 가 og:image / twitter:image 자동 생성)",
                "",
                "변경 글:",
            ]
            for c in changes:
                msg_lines.append(
                    f"- {c['name']}: dedup={c['dedup_removed']} src={c['src_removed_idx']}"
                    f" fm_empty={c['fm_sources_emptied']} image={c['image_added']}"
                )
            msg_lines.append("")
            msg_lines.append("Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>")
            pushed = git_commit_push(blog_root, "\n".join(msg_lines))
            if pushed:
                print(f"  → {blog_root.name} push 완료")
        else:
            print("  (변경 없음)")

    print("\n=== 요약 ===")
    for name, changes in overall_changes.items():
        print(f"{name}: {len(changes)} 편 갱신")


if __name__ == "__main__":
    main()
