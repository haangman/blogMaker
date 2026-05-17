"""페르소나 분석 파이프라인 — on-demand CLI 에서만 호출."""

from src.persona.analyzer import analyze
from src.persona.fetcher import fetch_articles, fetch_bodies, save_samples
from src.persona.merger import save_generated

__all__ = ["fetch_articles", "fetch_bodies", "save_samples", "analyze", "save_generated"]
