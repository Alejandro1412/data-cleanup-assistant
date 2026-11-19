from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_service
from app.llm.reviewer import AIReviewer
from app.main import app
from app.services import DatasetService
from app.storage.repository import Repository
from tests.helpers import FakeProvider


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, anthropic_api_key=None)


@pytest.fixture
def make_client(settings: Settings) -> Iterator[Callable[[FakeProvider | None], TestClient]]:
    def factory(provider: FakeProvider | None = None) -> TestClient:
        reviewer = AIReviewer(provider) if provider else None
        service = DatasetService(settings, Repository(settings.database_path), reviewer)
        app.dependency_overrides[get_service] = lambda: service
        return TestClient(app)

    yield factory
    app.dependency_overrides.clear()
