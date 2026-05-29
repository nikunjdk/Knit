import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# Set test env vars before any app.* imports so pydantic-settings always has values.
# Uses setdefault so CI-injected vars (if any) take priority over these defaults.
_TEST_ENV = {
    "SUPABASE_URL": "http://localhost",
    "SUPABASE_SERVICE_ROLE_KEY": "test",
    "SUPABASE_JWT_SECRET": "test-secret-at-least-32-chars-long!!",
    "GEMINI_API_KEY": "test",
    "LINKD_API_KEY": "test",
    "UPSTASH_REDIS_URL": "http://localhost",
    "UPSTASH_REDIS_TOKEN": "test",
    "ENVIRONMENT": "qa",
    "LOG_LEVEL": "DEBUG",
}
for _k, _v in _TEST_ENV.items():
    os.environ.setdefault(_k, _v)


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def mock_supabase(mocker):
    """MagicMock for the Supabase client — builder chain is sync, only .execute() is async."""
    client = MagicMock()
    mocker.patch("app.core.supabase.get_supabase_client", new_callable=AsyncMock, return_value=client)
    return client


@pytest.fixture
def mock_redis(mocker):
    client = AsyncMock()
    mocker.patch("app.core.redis.get_redis_client", return_value=client)
    return client


@pytest.fixture
def mock_gemini_embed(mocker):
    return mocker.patch("app.services.gemini.embed_text", new_callable=AsyncMock)


@pytest.fixture
def mock_gemini_stream(mocker):
    return mocker.patch("app.services.gemini.generate_stream", new_callable=AsyncMock)


@pytest.fixture
def mock_linkd(mocker):
    return mocker.patch("app.services.linkd.get_profile", new_callable=AsyncMock)


@pytest.fixture
def valid_jwt_headers():
    """Pre-signed JWT for user_id 00000000-0000-0000-0000-000000000001, matches test env secret."""
    from jose import jwt as jose_jwt

    token = jose_jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001", "role": "authenticated"},
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
