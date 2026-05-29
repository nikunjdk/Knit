from pydantic import BaseModel


class EnrichProfileRequest(BaseModel):
    linkedin_url: str


class EnrichProfileResponse(BaseModel):
    full_name: str | None = None
    role: str | None = None
    company: str | None = None
    interests: list[str] = []
    linkedin_url: str | None = None
    avatar_url: str | None = None


class EmbeddingRecomputeRequest(BaseModel):
    event_id: str | None = None
