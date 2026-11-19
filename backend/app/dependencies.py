from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.cache import CachedProvider, CacheStore
from app.llm.reviewer import AIReviewer
from app.services import DatasetService
from app.storage.repository import Repository


def build_reviewer(settings: Settings, cache: CacheStore) -> AIReviewer | None:
    if not settings.anthropic_api_key:
        return None
    provider = AnthropicProvider(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    return AIReviewer(CachedProvider(provider, cache))


def build_service(settings: Settings) -> DatasetService:
    repository = Repository(settings.database_path)
    return DatasetService(settings, repository, build_reviewer(settings, repository))


@lru_cache
def get_service() -> DatasetService:
    return build_service(get_settings())
