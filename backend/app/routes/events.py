from fastapi import APIRouter, HTTPException, Query

from app.models.events import EventLookupResponse

router = APIRouter(tags=["events"])


@router.get("/events/lookup", response_model=EventLookupResponse)
async def lookup_event(
    join_code: str = Query(..., min_length=1, max_length=10, pattern=r"^[A-Z0-9]+$"),
):
    raise HTTPException(status_code=501, detail="Not implemented")
