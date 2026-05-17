"""로컬 임시 이미지를 J-Blog/assets/img/YYYY/MM/ 로 복사 후 baseurl 기준 상대경로 반환."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.utils.timeutil import now_seoul


def copy_image(jblog_root: Path, local_image: Path, slug: str, *, index: int = 0) -> str:
    """index=0 은 헤더, 1+ 는 본문 이미지. 파일명에 index 가 들어가 충돌 회피."""
    when = now_seoul()
    sub = f"assets/img/{when:%Y/%m}"
    target_dir = jblog_root / sub
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = local_image.suffix.lower() or ".jpg"
    suffix = "" if index == 0 else f"-{index}"
    target = target_dir / f"{slug}{suffix}{ext}"
    shutil.copy2(local_image, target)
    return f"{sub}/{target.name}"
