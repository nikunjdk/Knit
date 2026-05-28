from datetime import date, time
from pydantic import BaseModel


class EventLookupResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    location: str | None = None
    start_date: date
    end_date: date
    start_time: time | None = None
    end_time: time | None = None
    agenda: str | None = None
    organizer_name: str
    attendee_count: int
    is_active: bool
