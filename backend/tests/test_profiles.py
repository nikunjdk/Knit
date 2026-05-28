from unittest.mock import AsyncMock, MagicMock


_TEST_USER = "00000000-0000-0000-0000-000000000001"
_JWT_SECRET = "test-secret-at-least-32-chars-long!!"


def _auth_headers():
    from jose import jwt
    token = jwt.encode({"sub": _TEST_USER, "role": "authenticated"}, _JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _linkd_response():
    return {
        "full_name": "Alice Smith",
        "headline": "Software Engineer at Acme Corp",
        "profile_pic_url": "https://example.com/pic.jpg",
        "skills": ["Python", "Machine Learning", "FastAPI"],
    }


def test_enrich_profile_happy_path(client, mocker):
    mocker.patch("app.routes.profiles.get_profile", new_callable=AsyncMock, return_value=_linkd_response())

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    mocker.patch("app.routes.profiles.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    mock_sb.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{}])
    )
    mocker.patch("app.routes.profiles.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    mocker.patch(
        "app.routes.profiles._map_interests_via_gemini",
        new_callable=AsyncMock,
        return_value=["AI/ML", "Engineer"],
    )

    r = client.post(
        "/enrich-profile",
        json={"linkedin_url": "https://linkedin.com/in/alicesmith"},
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "Software Engineer"
    assert data["company"] == "Acme Corp"
    assert data["full_name"] == "Alice Smith"


def test_enrich_profile_no_usable_data(client, mocker):
    mocker.patch("app.routes.profiles.get_profile", new_callable=AsyncMock, return_value={})
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mocker.patch("app.routes.profiles.get_redis_client", return_value=mock_redis)

    r = client.post(
        "/enrich-profile",
        json={"linkedin_url": "https://linkedin.com/in/nobody"},
        headers=_auth_headers(),
    )
    assert r.status_code == 422


def test_enrich_profile_linkd_timeout(client, mocker):
    import httpx
    mocker.patch("app.routes.profiles.get_profile", side_effect=httpx.TimeoutException("timeout"))

    r = client.post(
        "/enrich-profile",
        json={"linkedin_url": "https://linkedin.com/in/alicesmith"},
        headers=_auth_headers(),
    )
    assert r.status_code == 503


def test_enrich_profile_no_auth(client):
    r = client.post("/enrich-profile", json={"linkedin_url": "https://linkedin.com/in/x"})
    assert r.status_code == 403


def test_enrich_profile_tag_mapping_returns_only_valid_tags(client, mocker):
    """Gemini must never return tags outside our 31-tag list."""
    mocker.patch("app.routes.profiles.get_profile", new_callable=AsyncMock, return_value=_linkd_response())
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    mocker.patch("app.routes.profiles.get_redis_client", return_value=mock_redis)
    mock_sb = MagicMock()
    mock_sb.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{}])
    )
    mocker.patch("app.routes.profiles.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    # Gemini returns a mix of valid and invalid tags
    mocker.patch(
        "app.routes.profiles._map_interests_via_gemini",
        new_callable=AsyncMock,
        return_value=["AI/ML", "NotAValidTag", "Engineer", "FAKE"],
    )

    r = client.post(
        "/enrich-profile",
        json={"linkedin_url": "https://linkedin.com/in/alicesmith"},
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    interests = r.json()["interests"]
    valid_tags = {"AI/ML", "Web Dev", "Mobile", "DevOps", "Data", "Cybersecurity", "Open Source",
                  "Blockchain", "Fintech", "Healthtech", "Edtech", "Climate", "SaaS", "Consumer",
                  "B2B", "Deep Tech", "Founder", "Engineer", "Designer", "PM", "Marketer",
                  "Researcher", "Investor", "Student", "Hiring", "Job Hunting", "Cofounder Search",
                  "Investing", "Mentoring", "Collaborating", "Learning"}
    assert all(t in valid_tags for t in interests)
    assert "NotAValidTag" not in interests
    assert "FAKE" not in interests
