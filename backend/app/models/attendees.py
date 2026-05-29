from pydantic import BaseModel


class AttendeeProfile(BaseModel):
    user_id: str
    full_name: str
    avatar_url: str | None = None
    role: str | None = None
    company: str | None = None
    interests: list[str] = []
    linkedin_url: str | None = None
    agenda: str | None = None
    is_visible: bool = True
