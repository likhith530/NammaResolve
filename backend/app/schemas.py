from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ComplaintCategory(StrEnum):
    GARBAGE = "garbage"
    POTHOLE = "pothole"
    STREETLIGHT = "streetlight"
    DRAINAGE = "drainage"
    WATER_LEAKAGE = "water_leakage"
    OTHER = "other"


class ComplaintCreate(BaseModel):
    category: ComplaintCategory
    description: str = Field(min_length=10, max_length=1200)
    area: str = Field(min_length=2, max_length=120)
    landmark: str | None = Field(default=None, max_length=200)


class ComplaintStatusUpdate(BaseModel):
    status: str = Field(pattern="^(RECEIVED|IN_PROGRESS|RESOLVED|REJECTED)$")


class ComplaintOut(BaseModel):
    complaint_id: str
    category: ComplaintCategory
    description: str
    area: str
    landmark: str | None
    status: str
    created_at: datetime


class VoiceSessionRequest(BaseModel):
    # A numeric Agora UID is generated on the server if the client doesn't provide one.
    pass


class VoiceSessionOut(BaseModel):
    app_id: str
    channel: str
    token: str
    uid: int
    agent_session_id: str
    expires_at: int
