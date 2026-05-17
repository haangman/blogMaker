"""다국어 임베딩.

기본: sentence-transformers paraphrase-multilingual-MiniLM-L12-v2.
폴백: PyTorch DLL 등 환경 문제로 sentence-transformers 가 import 안 될 때
TF-IDF (char_wb n-gram) + TruncatedSVD 로 dense low-dim 벡터를 만든다.
출력 차원은 항상 384 로 padding 해서 다운스트림 인터페이스를 유지한다.
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

from src.config_loader import get_settings
from src.logging_setup import get_logger

log = get_logger("cluster.embed")

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIM = 384


@lru_cache(maxsize=1)
def _st_model():
    settings = get_settings()
    if settings.hf_home:
        os.environ.setdefault("HF_HOME", settings.hf_home)
    from sentence_transformers import SentenceTransformer

    log.info("embed.loading_model", name=MODEL_NAME)
    return SentenceTransformer(MODEL_NAME)


def _embed_st(texts: list[str]) -> np.ndarray:
    model = _st_model()
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def _embed_tfidf(texts: list[str]) -> np.ndarray:
    """sentence-transformers 가 안 될 때의 폴백. 한·영 모두 char_wb n-gram 으로 처리."""
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(
        max_features=20000,
        analyzer="char_wb",
        ngram_range=(2, 4),
        lowercase=True,
        min_df=1,
    )
    X = vec.fit_transform(texts)

    n_samples, n_feats = X.shape
    if n_samples == 0 or n_feats == 0:
        return np.zeros((n_samples, DIM), dtype=np.float32)

    n_comp = min(96, max(2, min(n_samples - 1, n_feats - 1)))
    if n_comp < 2:
        # 표본이 1개라 SVD 불가 — 그냥 첫 행 정규화
        arr = np.asarray(X.todense(), dtype=np.float32)
        if arr.shape[1] >= DIM:
            return arr[:, :DIM]
        pad = np.zeros((arr.shape[0], DIM - arr.shape[1]), dtype=np.float32)
        return np.concatenate([arr, pad], axis=1)

    svd = TruncatedSVD(n_components=n_comp, random_state=42)
    emb = svd.fit_transform(X)
    norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9
    emb = emb / norms
    if emb.shape[1] < DIM:
        pad = np.zeros((emb.shape[0], DIM - emb.shape[1]), dtype=np.float32)
        emb = np.concatenate([emb, pad], axis=1)
    elif emb.shape[1] > DIM:
        emb = emb[:, :DIM]
    return np.asarray(emb, dtype=np.float32)


_USE_FALLBACK: bool | None = None


def embed(texts: list[str]) -> np.ndarray:
    global _USE_FALLBACK
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)

    if _USE_FALLBACK is None:
        try:
            return _embed_st(texts)
        except Exception as e:
            log.warning(
                "embed.fallback_to_tfidf",
                reason=str(e)[:300],
            )
            _USE_FALLBACK = True

    if _USE_FALLBACK:
        return _embed_tfidf(texts)
    return _embed_st(texts)
