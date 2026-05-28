import json
from unittest.mock import AsyncMock, MagicMock

_ORGANIZER_ID = "00000000-0000-0000-0000-000000000001"
_ATTENDEE_A = "00000000-0000-0000-0000-000000000002"
_ATTENDEE_B = "00000000-0000-0000-0000-000000000003"
_EVENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


def _auth_headers(user_id=_ORGANIZER_ID):
    import os
    from jose import jwt
    token = jwt.encode(
        {"sub": user_id, "role": "authenticated"},
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


def _mock_event(count=0):
    return {
        "id": _EVENT_ID,
        "organizer_id": _ORGANIZER_ID,
        "digest_generation_count": count,
        "title": "Test Meetup",
    }


def _mock_attendees():
    return [
        {"user_id": _ATTENDEE_A, "profiles": {"interests": ["AI/ML", "SaaS"]}},
        {"user_id": _ATTENDEE_B, "profiles": {"interests": ["AI/ML", "Mobile"]}},
    ]


def _mock_connections(count=1):
    return [{"id": f"c{i}"} for i in range(count)]


def _setup_mocks(mocker, event=None, attendees=None, connections=None, cb_open=False):
    async def _fake_stream(prompt):
        yield "Great event!"

    mocker.patch("app.routes.digest.generate_stream", side_effect=_fake_stream)

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value="1" if cb_open else None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mocker.patch("app.routes.digest.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    # event fetch
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=MagicMock(data=event or _mock_event())
    )
    # attendees fetch (use `is not None` so empty list [] is respected)
    mock_sb.table.return_value.select.return_value.eq.return_value.execute = AsyncMock(
        return_value=MagicMock(data=attendees if attendees is not None else _mock_attendees())
    )
    # atomic increment (UPDATE ... RETURNING)
    mock_sb.rpc.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{"digest_generation_count": 1}])
    )
    mocker.patch("app.routes.digest.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)
    return mock_sb, mock_redis


def test_organizer_generates_digest(client, mocker):
    mock_sb, _ = _setup_mocks(mocker)

    r = client.get(f"/digest/stream?event_id={_EVENT_ID}", headers=_auth_headers())
    assert r.status_code == 200
    events = _parse_sse(r.text)
    stats_events = [e for e in events if "stats" in e]
    assert len(stats_events) == 1
    stats = stats_events[0]["stats"]
    assert "attendee_count" in stats
    assert "connection_density" in stats
    assert "top_tags" in stats
    chunks = [e["chunk"] for e in events if "chunk" in e]
    assert "Great event!" in "".join(chunks)
    done_events = [e for e in events if e.get("done") is True]
    assert len(done_events) == 1
    assert "generations_remaining" in done_events[0]


def test_digest_cap_reached(client, mocker):
    """digest_generation_count == 3 → 403 before Gemini."""
    mock_stream = mocker.patch("app.routes.digest.generate_stream")

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mocker.patch("app.routes.digest.get_redis_client", return_value=mock_redis)

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=MagicMock(data=_mock_event(count=3))
    )
    mocker.patch("app.routes.digest.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.get(f"/digest/stream?event_id={_EVENT_ID}", headers=_auth_headers())
    assert r.status_code == 403
    assert "DIGEST_CAP_REACHED" in r.text
    mock_stream.assert_not_called()


def test_non_organizer_forbidden(client, mocker):
    """Non-organizer → 403 before anything."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=MagicMock(data=_mock_event())  # organizer_id != _ATTENDEE_A
    )
    mocker.patch("app.routes.digest.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mocker.patch("app.routes.digest.get_redis_client", return_value=mock_redis)

    r = client.get(
        f"/digest/stream?event_id={_EVENT_ID}",
        headers=_auth_headers(user_id=_ATTENDEE_A),
    )
    assert r.status_code == 403


def test_circuit_breaker_open(client, mocker):
    mock_stream = mocker.patch("app.routes.digest.generate_stream")
    _setup_mocks(mocker, cb_open=True)

    r = client.get(f"/digest/stream?event_id={_EVENT_ID}", headers=_auth_headers())
    assert r.status_code == 429
    mock_stream.assert_not_called()


def test_stats_no_div_by_zero_with_zero_connections(client, mocker):
    """connection_density must not crash with 0 attendees or 0 connections."""
    mock_sb, _ = _setup_mocks(mocker, attendees=[])

    r = client.get(f"/digest/stream?event_id={_EVENT_ID}", headers=_auth_headers())
    assert r.status_code == 200
    events = _parse_sse(r.text)
    stats = next(e["stats"] for e in events if "stats" in e)
    assert stats["connection_density"] == 0.0
    assert stats["attendee_count"] == 0
