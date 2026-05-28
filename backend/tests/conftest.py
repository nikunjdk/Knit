import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_supabase(mocker):
    return mocker.patch("app.core.supabase.get_supabase_client", return_value=AsyncMock())


@pytest.fixture
def mock_redis(mocker):
    return mocker.patch("app.core.redis.get_redis_client", return_value=AsyncMock())


@pytest.fixture
def mock_gemini(mocker):
    return mocker.patch("app.services.gemini.embed_text", new_callable=AsyncMock)
