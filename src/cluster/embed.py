"""다국어 임베딩 — sentence-transformers 의 paraphrase-multilingual-MiniLM-L12-v2.

처음 호출되면 모델을 캐시 디렉토리(HF_HOME)에 다운로드한다.
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

from src.config_loader import get_settings
from src.logging_setup import get_logger

log = get_logger("cluster.embed")

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def _model():
    settings = get_settings()
    if settings.hf_home:
        os.environ.setdefault("HF_HOME", settings.hf_home)
    from sentence_transformers import SentenceTransformer

    log.info("embed.loading_model", name=MODEL_NAME)
    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    model = _model()
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)
