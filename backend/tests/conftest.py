import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock


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
    import os
    from jose import jwt as jose_jwt

    secret = os.environ.get("SUPABASE_JWT_SECRET", "test-secret-at-least-32-chars-long!!")
    token = jose_jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001", "role": "authenticated"},
        secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
