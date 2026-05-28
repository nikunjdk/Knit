from unittest.mock import AsyncMock, MagicMock

_TEST_USER = "00000000-0000-0000-0000-000000000001"
_OTHER_USER_A = "00000000-0000-0000-0000-000000000002"
_OTHER_USER_B = "00000000-0000-0000-0000-000000000003"
_EVENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
_FAKE_VECTOR = [0.1] * 768


def _auth_headers():
    import os

    from jose import jwt

    token = jwt.encode(
        {"sub": _TEST_USER, "role": "authenticated"},
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _make_profile_row(user_id=_TEST_USER):
    return {"id": user_id, "role": "Engineer", "company": "Acme", "interests": ["AI/ML"]}


def _make_attendee_row(user_id, embedding=None):
    return {"user_id": user_id, "event_embedding": embedding}


def test_recompute_profile_only(client, mocker):
    """Profile-only recompute (no event_id) — embeds and patches profile_embedding."""
    mock_embed = mocker.patch("app.routes.embeddings.embed_text", new_callable=AsyncMock, return_value=_FAKE_VECTOR)

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mocker.patch("app.routes.embeddings.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=MagicMock(data=_make_profile_row())
    )
    mock_sb.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{}])
    )
    mocker.patch("app.routes.embeddings.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.post("/embeddings/recompute", json={}, headers=_auth_headers())
    assert r.status_code == 202
    mock_embed.assert_called_once()
    # Should NOT try to upsert scores (no event_id)
    assert mock_sb.table.return_value.upsert.call_count == 0


def test_recompute_with_event_produces_scores(client, mocker):
    """Full recompute with event_id — embeds, patches event_embedding, upserts scores for other attendees."""
    mock_embed = mocker.patch("app.routes.embeddings.embed_text", new_callable=AsyncMock, return_value=_FAKE_VECTOR)

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mocker.patch("app.routes.embeddings.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    # Profile fetch
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=MagicMock(data=_make_profile_row())
    )
    # Attendees fetch (returns 2 other users with embeddings)
    mock_sb.table.return_value.select.return_value.eq.return_value.neq.return_value.execute = AsyncMock(
        return_value=MagicMock(
            data=[
                _make_attendee_row(_OTHER_USER_A, _FAKE_VECTOR),
                _make_attendee_row(_OTHER_USER_B, _FAKE_VECTOR),
            ]
        )
    )
    mock_sb.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{}])
    )
    mock_sb.table.return_value.upsert.return_value.execute = AsyncMock(return_value=MagicMock(data=[{}]))
    mocker.patch("app.routes.embeddings.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.post("/embeddings/recompute", json={"event_id": _EVENT_ID}, headers=_auth_headers())
    assert r.status_code == 202
    # embed_text called twice: once for profile, once with agenda appended
    assert mock_embed.call_count == 2
    # Scores upserted for 2 other attendees
    assert mock_sb.table.return_value.upsert.call_count == 2


def test_recompute_circuit_breaker_open(client, mocker):
    """Circuit breaker open → 429, Gemini never called."""
    mock_embed = mocker.patch("app.routes.embeddings.embed_text", new_callable=AsyncMock)

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value="1")  # circuit_breaker:open is set
    mocker.patch("app.routes.embeddings.get_redis_client", return_value=mock_redis)

    r = client.post("/embeddings/recompute", json={}, headers=_auth_headers())
    assert r.status_code == 429
    mock_embed.assert_not_called()


def test_recompute_null_profile_fields(client, mocker):
    """Null role/company/interests must not produce 'None at None' embedding text."""
    captured_texts: list[str] = []

    async def _capture_embed(text):
        captured_texts.append(text)
        return _FAKE_VECTOR

    mocker.patch("app.routes.embeddings.embed_text", side_effect=_capture_embed)

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mocker.patch("app.routes.embeddings.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=MagicMock(data={"id": _TEST_USER, "role": None, "company": None, "interests": []})
    )
    mock_sb.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{}])
    )
    mocker.patch("app.routes.embeddings.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.post("/embeddings/recompute", json={}, headers=_auth_headers())
    assert r.status_code == 202
    assert len(captured_texts) == 1
    assert "None" not in captured_texts[0]


def test_recompute_no_auth(client):
    r = client.post("/embeddings/recompute", json={})
    assert r.status_code == 403
