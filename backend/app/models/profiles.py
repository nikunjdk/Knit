from pydantic import BaseModel


class EnrichProfileRequest(BaseModel):
    linkedin_url: str


class EnrichProfileResponse(BaseModel):
    """Enriched profile data returned to the client after LinkedIn lookup."""

    full_name: str | None = None
    role: str | None = None
    company: str | None = None
    interests: list[str] = []
    linkedin_url: str | None = None
    avatar_url: str | None = None


class EmbeddingRecomputeRequest(BaseModel):
    # When event_id is None, only the cross-event profile embedding is recomputed (no scoring).
    event_id: str | None = None
