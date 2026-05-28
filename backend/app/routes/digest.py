from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import verify_jwt

router = APIRouter(tags=["digest"])


@router.get("/digest/stream")
async def stream_digest(
    event_id: str = Query(...),
    user_id: str = Depends(verify_jwt),
):
    raise HTTPException(status_code=501, detail="Not implemented")
