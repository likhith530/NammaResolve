from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import get_settings
from backend.app.database import (
    create_complaint,
    get_complaint,
    init_db,
    list_complaints,
)
from backend.app.schemas import ComplaintCreate, ComplaintOut, VoiceSessionOut
from backend.app.services.agora import start_voice_session, stop_voice_session


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="NammaResolve API",
    description="A voice-first civic issue reporting assistant for Bengaluru residents.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "NammaResolve"}


@app.get("/api/complaints", response_model=list[ComplaintOut])
def complaints(limit: int = Query(default=50, ge=1, le=100)):
    return list_complaints(limit=limit)


@app.post("/api/complaints", response_model=ComplaintOut, status_code=201)
def submit_complaint(payload: ComplaintCreate):
    """Create a complaint directly from the website form."""
    return create_complaint(payload)


@app.get("/api/complaints/{complaint_id}", response_model=ComplaintOut)
def complaint_detail(complaint_id: str):
    result = get_complaint(complaint_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return result


def verify_tool_key(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().tool_secret
    if not expected or expected == "replace-with-a-long-random-secret":
        raise HTTPException(status_code=503, detail="Tool API key is not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid tool credentials")


@app.post("/api/tools/complaints", response_model=ComplaintOut, dependencies=[Depends(verify_tool_key)])
def create_complaint_tool(payload: ComplaintCreate):
    """Agora custom tool: create a resident-confirmed complaint."""
    return create_complaint(payload)


@app.get(
    "/api/tools/complaints/{complaint_id}",
    response_model=ComplaintOut,
    dependencies=[Depends(verify_tool_key)],
)
def get_complaint_tool(complaint_id: str):
    """Agora custom tool: retrieve the current status of a complaint."""
    result = get_complaint(complaint_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No NammaResolve complaint matches that reference")
    return result


@app.post("/api/voice/session", response_model=VoiceSessionOut)
def create_voice_session():
    """Start an Agora Conversational AI session using Murf Falcon TTS."""
    try:
        session = start_voice_session()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface a safe setup error to the UI
        raise HTTPException(status_code=502, detail=f"Could not start Agora voice session: {exc}") from exc

    settings = get_settings()
    return VoiceSessionOut(
        app_id=settings.agora_app_id,
        channel=session.channel,
        token=session.token,
        uid=session.uid,
        agent_session_id=session.agent_session_id,
        expires_at=session.expires_at,
    )


@app.post("/api/voice/session/{agent_session_id}/stop")
def end_voice_session(agent_session_id: str):
    """Stop the voice agent session when the resident ends the call."""
    try:
        stopped = stop_voice_session(agent_session_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not stop Agora session: {exc}") from exc
    return {"stopped": stopped}


FRONTEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[2] / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(FRONTEND_DIR / "index.html")
