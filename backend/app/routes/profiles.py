from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_jwt
from app.models.profiles import EnrichProfileRequest, EnrichProfileResponse

router = APIRouter(tags=["profiles"])


@router.post("/enrich-profile", response_model=EnrichProfileResponse)
async def enrich_profile(
    body: EnrichProfileRequest,
    user_id: str = Depends(verify_jwt),
):
    raise HTTPException(status_code=501, detail="Not implemented")
