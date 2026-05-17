"""로컬 임시 이미지를 J-Blog/assets/img/YYYY/MM/ 로 복사하고 site.baseurl 기준 상대경로 반환."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.utils.timeutil import now_seoul


def copy_image(jblog_root: Path, local_image: Path, slug: str) -> str:
    when = now_seoul()
    sub = f"assets/img/{when:%Y/%m}"
    target_dir = jblog_root / sub
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = local_image.suffix.lower() or ".jpg"
    target = target_dir / f"{slug}{ext}"
    shutil.copy2(local_image, target)
    return f"{sub}/{target.name}"
