import json
from unittest.mock import AsyncMock, MagicMock

_TEST_USER = "00000000-0000-0000-0000-000000000001"
_OTHER_USER = "00000000-0000-0000-0000-000000000002"
_EVENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
# canonical order: _TEST_USER < _OTHER_USER (lexicographic)
_UID_A, _UID_B = sorted([_TEST_USER, _OTHER_USER])


def _auth_headers():
    import os
    from jose import jwt
    token = jwt.encode(
        {"sub": _TEST_USER, "role": "authenticated"},
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def _attendees_data():
    return [
        {"user_id": _TEST_USER, "agenda": "Find cofounders",
         "profiles": {"role": "Engineer", "company": "Acme", "interests": ["AI/ML"]}},
        {"user_id": _OTHER_USER, "agenda": "Meet investors",
         "profiles": {"role": "PM", "company": "Beta", "interests": ["SaaS"]}},
    ]


def test_redis_cache_hit_no_gemini(client, mocker):
    """Redis hit — Gemini never called, cached content streamed immediately."""
    mock_stream = mocker.patch("app.routes.icebreaker.generate_stream")

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value="Cached icebreaker text")
    mocker.patch("app.routes.icebreaker.get_redis_client", return_value=mock_redis)

    r = client.get(
        f"/icebreaker/stream?event_id={_EVENT_ID}&other_user_id={_OTHER_USER}",
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/event-stream; charset=utf-8"
    events = _parse_sse(r.text)
    assert any(e.get("chunk") == "Cached icebreaker text" for e in events)
    assert any(e.get("done") is True for e in events)
    mock_stream.assert_not_called()


def test_postgres_cache_hit_writes_redis(client, mocker):
    """Postgres hit — writes to Redis, no Gemini call."""
    mock_stream = mocker.patch("app.routes.icebreaker.generate_stream")

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)   # Redis miss
    mock_redis.set = AsyncMock()
    mocker.patch("app.routes.icebreaker.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    # icebreaker_cache: Postgres hit
    mock_sb.table.return_value.select.return_value.eq.return_value \
        .eq.return_value.eq.return_value.maybe_single.return_value.execute = AsyncMock(
            return_value=MagicMock(data={"content": "PG cached text"})
        )
    mocker.patch("app.routes.icebreaker.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.get(
        f"/icebreaker/stream?event_id={_EVENT_ID}&other_user_id={_OTHER_USER}",
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    events = _parse_sse(r.text)
    assert any(e.get("chunk") == "PG cached text" for e in events)
    # Redis.set must have been called to warm the cache
    mock_redis.set.assert_called_once()
    mock_stream.assert_not_called()


def test_full_generation_caches_result(client, mocker):
    """Both caches miss — Gemini generates, result cached in Postgres + Redis."""
    async def _fake_stream(prompt):
        yield "Hello "
        yield "world!"

    mocker.patch("app.routes.icebreaker.generate_stream", side_effect=_fake_stream)

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mocker.patch("app.routes.icebreaker.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    # icebreaker_cache: Postgres miss
    mock_sb.table.return_value.select.return_value.eq.return_value \
        .eq.return_value.eq.return_value.maybe_single.return_value.execute = AsyncMock(
            return_value=MagicMock(data=None)
        )
    # event_attendees fetch
    mock_sb.table.return_value.select.return_value.eq.return_value \
        .in_.return_value.execute = AsyncMock(
            return_value=MagicMock(data=_attendees_data())
        )
    # upsert icebreaker_cache
    mock_sb.table.return_value.upsert.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{}])
    )
    mocker.patch("app.routes.icebreaker.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.get(
        f"/icebreaker/stream?event_id={_EVENT_ID}&other_user_id={_OTHER_USER}",
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    events = _parse_sse(r.text)
    chunks = [e["chunk"] for e in events if "chunk" in e]
    assert "".join(chunks) == "Hello world!"
    assert any(e.get("done") is True for e in events)
    # Redis set must be called (cache write)
    mock_redis.set.assert_called()
    # Postgres upsert must be called
    mock_sb.table.return_value.upsert.assert_called_once()


def test_circuit_breaker_open_before_generation(client, mocker):
    """Both caches miss, circuit breaker open → 429 before Gemini."""
    mock_stream = mocker.patch("app.routes.icebreaker.generate_stream")

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(side_effect=[None, "1"])  # first get=miss, second get=CB open
    mocker.patch("app.routes.icebreaker.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value \
        .eq.return_value.eq.return_value.maybe_single.return_value.execute = AsyncMock(
            return_value=MagicMock(data=None)
        )
    mocker.patch("app.routes.icebreaker.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.get(
        f"/icebreaker/stream?event_id={_EVENT_ID}&other_user_id={_OTHER_USER}",
        headers=_auth_headers(),
    )
    assert r.status_code == 429
    mock_stream.assert_not_called()


def test_users_not_in_same_event(client, mocker):
    """One user missing from event_attendees → 404."""
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(side_effect=[None, None])  # both cache misses, CB not open
    mocker.patch("app.routes.icebreaker.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value \
        .eq.return_value.eq.return_value.maybe_single.return_value.execute = AsyncMock(
            return_value=MagicMock(data=None)
        )
    # Only one attendee returned
    mock_sb.table.return_value.select.return_value.eq.return_value \
        .in_.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[_attendees_data()[0]])  # only TEST_USER
        )
    mocker.patch("app.routes.icebreaker.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.get(
        f"/icebreaker/stream?event_id={_EVENT_ID}&other_user_id={_OTHER_USER}",
        headers=_auth_headers(),
    )
    assert r.status_code == 404
