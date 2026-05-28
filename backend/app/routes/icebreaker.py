from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import verify_jwt

router = APIRouter(tags=["icebreaker"])


@router.get("/icebreaker/stream")
async def stream_icebreaker(
    event_id: str = Query(...),
    other_user_id: str = Query(...),
    user_id: str = Depends(verify_jwt),
):
    raise HTTPException(status_code=501, detail="Not implemented")
