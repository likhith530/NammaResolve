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
    voice_session_id: str | None = Field(default=None, max_length=200)
    confirmation_status: str | None = Field(default=None, pattern="^(pending_confirmation|confirmed)$")


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
    voice_session_id: str | None = None
    confirmation_status: str = "confirmed"
    proof_filename: str | None = None
    proof_content_type: str | None = None
    proof_size: int | None = None
    proof_url: str | None = None


class VoiceSessionRequest(BaseModel):
    language: str = Field(default="kn-IN", pattern="^(en-US|kn-IN)$")


class VoiceSessionOut(BaseModel):
    app_id: str
    channel: str
    token: str
    uid: int
    agent_session_id: str
    expires_at: int


class TranscriptEntry(BaseModel):
    speaker: str = Field(pattern="^(resident|agent|system)$")
    text: str = Field(min_length=1, max_length=4000)
    is_final: bool = True


class POCInfo(BaseModel):
    area: str
    constituency: str
    mla_name: str
    mla_email: str
    poc_name: str
    poc_email: str
    is_demo: bool = True


class EmailPreview(BaseModel):
    complaint_id: str
    to: list[str]
    subject: str
    body: str
    sent: bool = False
    is_demo: bool = True


class TranscriptEntryOut(TranscriptEntry):
    entry_id: int
    timestamp: datetime
