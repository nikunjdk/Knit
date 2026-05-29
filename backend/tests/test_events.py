from unittest.mock import AsyncMock, MagicMock


def _mock_event_row():
    return {
        "id": "evt-0000-0000-0000-000000000001",
        "title": "Test Meetup",
        "description": "A great meetup",
        "location": "Bangalore",
        "start_date": "2026-06-01",
        "end_date": "2026-06-01",
        "start_time": "18:00:00",
        "end_time": "21:00:00",
        "agenda": "Networking + talks",
        "is_active": True,
        "profiles": {"full_name": "Alice"},
        "event_attendees": [{"user_id": "u1"}, {"user_id": "u2"}],
    }


def _make_supabase_mock(data):
    """Supabase client uses a synchronous builder chain; only .execute() is async."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute = AsyncMock(
        return_value=MagicMock(data=data)
    )
    return mock_sb


def test_lookup_event_happy_path(client, mocker):
    mock_sb = _make_supabase_mock(_mock_event_row())
    mocker.patch("app.routes.events.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.get("/events/lookup?join_code=ABC12")
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Test Meetup"
    assert data["organizer_name"] == "Alice"
    assert data["attendee_count"] == 2
    assert data["is_active"] is True


def test_lookup_event_not_found(client, mocker):
    mock_sb = _make_supabase_mock(None)
    mocker.patch("app.routes.events.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.get("/events/lookup?join_code=XXXXX")
    assert r.status_code == 404


def test_lookup_event_inactive(client, mocker):
    row = _mock_event_row()
    row["is_active"] = False
    mock_sb = _make_supabase_mock(row)
    mocker.patch("app.routes.events.get_supabase_client", new_callable=AsyncMock, return_value=mock_sb)

    r = client.get("/events/lookup?join_code=ABC12")
    assert r.status_code == 410


def test_lookup_event_invalid_join_code_lowercase(client):
    r = client.get("/events/lookup?join_code=abc12")
    assert r.status_code == 422


def test_lookup_event_invalid_join_code_too_long(client):
    r = client.get("/events/lookup?join_code=ABCDE12345X")
    assert r.status_code == 422


def test_lookup_event_missing_join_code(client):
    r = client.get("/events/lookup")
    assert r.status_code == 422
