"""Public event lookup — no auth required; used for the pre-join event preview screen."""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.core.supabase import get_supabase_client
from app.models.events import EventLookupResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["events"])


@router.get("/events/lookup", response_model=EventLookupResponse, summary="Look up event by join code")
async def lookup_event(
    join_code: str = Query(..., min_length=1, max_length=10, pattern=r"^[A-Z0-9]+$"),
):
    """Return a public event snapshot by join code. No authentication required.

    Called before the Google OAuth redirect so the user sees event details before signing in.
    Returns 404 if the join code doesn't exist; 410 if the event has ended (is_active=false).
    """
    sb = await get_supabase_client()
    try:
        result = (
            await sb.table("events")
            .select("*, profiles(full_name), event_attendees(user_id)")
            .eq("join_code", join_code)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Supabase error on event lookup")
        raise HTTPException(status_code=500, detail="Failed to fetch event")

    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    row = result.data

    if not row["is_active"]:
        raise HTTPException(status_code=410, detail="Event has ended")

    organizer = row.get("profiles") or {}
    attendees = row.get("event_attendees") or []

    return EventLookupResponse(
        id=row["id"],
        title=row["title"],
        description=row.get("description"),
        location=row.get("location"),
        start_date=row["start_date"],
        end_date=row["end_date"],
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        agenda=row.get("agenda"),
        organizer_name=organizer.get("full_name", "Unknown"),
        attendee_count=len(attendees),
        is_active=row["is_active"],
    )
