from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_jwt
from app.models.profiles import EmbeddingRecomputeRequest

router = APIRouter(tags=["embeddings"])


@router.post("/embeddings/recompute", status_code=202)
async def recompute_embeddings(
    body: EmbeddingRecomputeRequest,
    user_id: str = Depends(verify_jwt),
):
    raise HTTPException(status_code=501, detail="Not implemented")
