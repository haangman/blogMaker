"""세 블로그 _posts 의 글에서 헤더+본문 이미지를 모두 모아 claude vision 으로 품질 평가.

평가 기준 두 측면:
1. 토픽 매칭 — 글 제목/요약과 이미지가 잘 어울리는가
2. 인공 부산물 — 왜곡된 얼굴, garbled 텍스트, 비현실적 합성 흔적, 일관성 깨짐

평가 결과 `replace=true` 인 이미지들에 대해:
  - 같은 alt 키워드로 Unsplash → Pexels 재시도
  - 이미지 파일 교체 (assets/img/.../slug-N.jpg 그대로)
  - 본문 크레딧 라인 교체 (Pollinations 크레딧 → Unsplash 크레딧)
  - frontmatter image/cover-img/header.overlay_image 는 절대 URL 그대로라 변경 불필요

사용:
  python -m scripts.audit_ai_images                  # 모든 블로그
  python -m scripts.audit_ai_images --blog J-Blog
  python -m scripts.audit_ai_images --since 2026-05-19  # 그 날짜 이후 글만
  python -m scripts.audit_ai_images --dry-run
  python -m scripts.audit_ai_images --max-evals 20    # 평가 횟수 상한
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import frontmatter

from src.images import pexels, unsplash
from src.llm import ask


# `![alt](url)` + 그 다음 줄 *[credit](credit_url)*
BODY_IMAGE_RE = re.compile(
    r'!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)\s*\n'
    r'\*\[(?P<credit>[^\]]+)\]\((?P<credit_url>[^)]+)\)\*'
)


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


@dataclass
class ImageRecord:
    blog: BlogTarget
    post_path: Path
    title: str
    summary: str
    alt: str
    url: str           # 절대 URL (frontmatter에 박힌 src)
    credit: str        # 'AI generated (Pollinations · Flux)' 또는 'Photo by ... on Unsplash'
    credit_url: str
    local_image_path: Path | None   # blog repo 안 assets/img/.../slug-N.jpg
    is_ai_generated: bool


def _slug_from_filename(p: Path) -> str:
    name = p.stem
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name)


def _url_to_local(url: str, blog: BlogTarget) -> Path | None:
    """절대 URL → 로컬 파일 경로 매핑."""
    marker = f"/{blog.repo_name}/assets/"
    if marker not in url:
        return None
    rel = url.split(marker, 1)[1]
    local = blog.repo_path / "assets" / rel
    return local if local.exists() else None


def collect_images(blog: BlogTarget, since_date: str | None = None) -> list[ImageRecord]:
    posts_dir = blog.repo_path / "_posts"
    if not posts_dir.exists():
        return []
    out: list[ImageRecord] = []
    for p in sorted(posts_dir.glob("*.md")):
        if since_date and p.name[:10] < since_date:
            continue
        try:
            post = frontmatter.load(str(p))
        except Exception:
            continue
        title = post.metadata.get("title", "")
        summary = post.metadata.get("summary") or post.metadata.get("description") or ""

        # 본문 마크다운 이미지 + 크레딧
        for m in BODY_IMAGE_RE.finditer(post.content):
            url = m.group("url").strip()
            credit = m.group("credit").strip()
            local = _url_to_local(url, blog)
            is_ai = "pollinations" in credit.lower() or "ai generated" in credit.lower()
            out.append(ImageRecord(
                blog=blog, post_path=p, title=title, summary=summary,
                alt=m.group("alt").strip(),
                url=url, credit=credit, credit_url=m.group("credit_url").strip(),
                local_image_path=local, is_ai_generated=is_ai,
            ))
        # 헤더 이미지: chirpy/beautiful-jekyll/minimal-mistakes 모두 frontmatter 만 사용
        # → 본문에 마크다운 없음. published 테이블에 provider 정보가 없으므로
        # 헤더 이미지의 provider 추정은 본문 이미지 결과로 대용 (사이클이 모든 이미지에
        # 동일 IMAGE_PROVIDER 사용했다는 가정).
    return out


_VISION_PROMPT_TEMPLATE = """다음 정보를 보고 이미지가 블로그 글에 사용하기 적합한지 평가해.

[글 제목] {title}
[글 요약] {summary}
[이미지 alt] {alt}
[이미지 파일] {image_path}

평가 기준:
1. 글의 토픽·분위기와 이미지가 어울리는가
2. 인공 부산물(왜곡된 사람 얼굴, 깨진 손가락, garbled 텍스트, 비현실적 합성, 색상 이상, 일관성 깨짐) 가 있는가
3. 사진 한 장으로 봤을 때 게재 부적절(저품질, 흐림, 잘림) 인가

JSON 한 줄로만 응답해 — 다른 설명 금지:
{{"relevant": true|false, "artifact": "none|distorted_face|garbled_text|unrealistic|broken_hands|low_quality|other", "replace": true|false, "reason": "한 줄"}}
"""


def evaluate_image(rec: ImageRecord) -> dict | None:
    if not rec.local_image_path or not rec.local_image_path.exists():
        return {"relevant": False, "artifact": "missing_file", "replace": False, "reason": "파일 없음"}

    prompt = _VISION_PROMPT_TEMPLATE.format(
        title=rec.title or "(제목 없음)",
        summary=(rec.summary or "")[:300],
        alt=rec.alt or "(alt 없음)",
        image_path=str(rec.local_image_path),
    )
    try:
        resp = ask(prompt, model="opus", purpose="image_quality_audit", timeout_s=120)
    except Exception as e:
        return {"relevant": False, "artifact": "eval_error", "replace": False, "reason": str(e)[:100]}

    text = (resp.text or "").strip()
    # JSON 본문 추출 — 첫 { 부터 마지막 } 까지
    if "{" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    try:
        return json.loads(text)
    except Exception:
        return {"relevant": False, "artifact": "parse_error", "replace": False, "reason": text[:100]}


def replace_image(rec: ImageRecord, *, dry_run: bool = False) -> tuple[bool, str]:
    """원래 alt 키워드로 Unsplash → Pexels 재시도, 이미지 파일 + 본문 크레딧 교체."""
    query = rec.alt or rec.title
    if not query:
        return False, "no_query"
    result = unsplash.search_and_download(query) or pexels.search_and_download(query)
    if not result:
        return False, "no_stock_found"

    new_path, meta = result
    if dry_run:
        return True, f"would_replace_with: {meta.get('credit')}"

    # 1. 로컬 파일 교체 (assets/img/.../slug-N.jpg)
    if rec.local_image_path:
        shutil.copy(new_path, rec.local_image_path)

    # 2. 글 본문 안의 마크다운 + 크레딧 줄을 교체
    post = frontmatter.load(str(rec.post_path))
    new_alt = (meta.get("alt") or query).strip()
    new_credit = meta.get("credit") or ""
    new_credit_url = meta.get("credit_url") or ""

    # 정확히 그 이미지(url 일치)의 alt + credit 만 바꿈
    old_pat = re.compile(
        rf'!\[[^\]]*\]\({re.escape(rec.url)}\)\s*\n'
        rf'\*\[[^\]]+\]\([^)]+\)\*'
    )
    if new_credit_url:
        replacement = f"![{new_alt}]({rec.url})\n*[{new_credit}]({new_credit_url})*"
    else:
        replacement = f"![{new_alt}]({rec.url})\n*{new_credit}*"
    new_content, n = old_pat.subn(replacement, post.content, count=1)
    if n == 0:
        return False, "regex_no_match"
    post.content = new_content

    # frontmatter image alt 도 업데이트 (chirpy) — 토픽 텍스트 alt 더 자연스러움
    if isinstance(post.metadata.get("image"), dict):
        post.metadata["image"]["alt"] = post.metadata.get("title") or new_alt

    rec.post_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return True, f"replaced→{new_credit}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog", choices=[b.name for b in DEFAULT_BLOGS], default=None)
    parser.add_argument("--since", default=None, help="YYYY-MM-DD — 이 날짜 이후 글만")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-evals", type=int, default=200, help="평가 호출 상한")
    parser.add_argument("--only-ai", action="store_true", default=False,
                        help="AI 생성 표시(Pollinations) 이미지만 평가")
    args = parser.parse_args()

    blogs = DEFAULT_BLOGS if args.blog is None else [b for b in DEFAULT_BLOGS if b.name == args.blog]
    if args.dry_run:
        print("[INFO] DRY RUN — no files written")

    all_records: list[ImageRecord] = []
    for blog in blogs:
        recs = collect_images(blog, since_date=args.since)
        if args.only_ai:
            recs = [r for r in recs if r.is_ai_generated]
        print(f"  · {blog.name}: {len(recs)} images")
        all_records.extend(recs)

    print(f"\n[INFO] {len(all_records)} images to evaluate (max {args.max_evals})")
    targets = all_records[: args.max_evals]

    flagged: list[tuple[ImageRecord, dict]] = []
    for i, rec in enumerate(targets, 1):
        print(f"  [{i}/{len(targets)}] {rec.post_path.name} :: {rec.alt[:40]}")
        verdict = evaluate_image(rec) or {}
        print(f"      → {verdict}")
        if verdict.get("replace"):
            flagged.append((rec, verdict))

    print(f"\n[INFO] {len(flagged)} flagged for replacement\n")
    replaced = 0
    failed: list[tuple[ImageRecord, str]] = []
    for rec, verdict in flagged:
        ok, msg = replace_image(rec, dry_run=args.dry_run)
        status = "✓" if ok else "✗"
        print(f"  {status} {rec.post_path.name} :: {rec.alt[:40]} — {msg}")
        if ok:
            replaced += 1
        else:
            failed.append((rec, msg))

    print(f"\n=== SUMMARY ===")
    print(f"  evaluated:  {len(targets)}")
    print(f"  flagged:    {len(flagged)}")
    print(f"  replaced:   {replaced}")
    print(f"  fallback failed: {len(failed)}")


if __name__ == "__main__":
    main()
