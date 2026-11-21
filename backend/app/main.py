import logging

logger = logging.getLogger(__name__)
from contextlib import asynccontextmanager

from io import BytesIO

from fastapi import Depends, FastAPI, Header, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse

from fastapi.staticfiles import StaticFiles

from backend.app.config import get_settings
from backend.app.database import (
    append_transcript_entry,
    attach_proof,
    create_complaint,
    get_complaint,
    init_db,
    list_complaints,
    list_transcript_entries,
)
from backend.app.schemas import ComplaintCreate, ComplaintOut, EmailPreview, POCInfo, TranscriptEntry, TranscriptEntryOut, VoiceSessionOut, VoiceSessionRequest
from backend.app.services.agora import start_voice_session, stop_voice_session

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def _wrap_pdf_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars:
            if current:
                lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


DEMO_POCS = [
    POCInfo(area="Kalyan Nagar", constituency="Sarvagnanagar", mla_name="Demo MLA - Sarvagnanagar", mla_email="mla.sarvagnanagar@example.com", poc_name="Kalyan Nagar", poc_email="poc.kalyannagar@example.com"),
    POCInfo(area="Jayanagar", constituency="Jayanagar", mla_name="Demo MLA - Jayanagar", mla_email="mla.jayanagar@example.com", poc_name="Jayanagar", poc_email="poc.jayanagar@example.com"),
    POCInfo(area="Indiranagar", constituency="Shanti Nagar", mla_name="Demo MLA - Shanti Nagar", mla_email="mla.shantinagar@example.com", poc_name="Indiranagar", poc_email="poc.indiranagar@example.com"),
    POCInfo(area="Whitefield", constituency="Mahadevapura", mla_name="Demo MLA - Mahadevapura", mla_email="mla.mahadevapura@example.com", poc_name="Whitefield", poc_email="poc.whitefield@example.com"),
]


def _matching_poc(area: str) -> POCInfo:
    area_lower = area.lower()
    for poc in DEMO_POCS:
        if poc.area.lower() in area_lower:
            return poc
    return POCInfo(area=area, constituency="Demo / Unmapped", mla_name="Demo Local Representative", mla_email="representative@example.com", poc_name="Demo Area POC", poc_email="poc@example.com")


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


@app.get("/api/pocs", response_model=list[POCInfo])
def list_demo_pocs():
    return DEMO_POCS


@app.get("/api/complaints/{complaint_id}/email-preview", response_model=EmailPreview)
def preview_complaint_email(complaint_id: str):
    complaint = get_complaint(complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    poc = _matching_poc(complaint.area)
    subject = f"NammaResolve demo report: {complaint.complaint_id} - {complaint.category.value}"
    body = (
        f"Demo civic report\n\n"
        f"Reference: {complaint.complaint_id}\n"
        f"Category: {complaint.category.value}\n"
        f"Area: {complaint.area}\n"
        f"Landmark: {complaint.landmark or 'Not provided'}\n"
        f"Description: {complaint.description}\n\n"
        f"Sent as a NammaResolve demo only. No real email was delivered."
    )
    return EmailPreview(
        complaint_id=complaint.complaint_id,
        to=[poc.mla_email, poc.poc_email],
        subject=subject,
        body=body,
        sent=False,
        is_demo=True,
    )


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


@app.post("/api/complaints/{complaint_id}/proof")
async def upload_complaint_proof(complaint_id: str, proof: UploadFile = File(...)):
    complaint = get_complaint(complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")

    proofs_dir = get_settings().database_file.parent / "proofs" / complaint_id.upper()
    proofs_dir.mkdir(parents=True, exist_ok=True)
    filename = proof.filename or "proof-upload"
    stored_path = proofs_dir / filename
    content = await proof.read()
    stored_path.write_bytes(content)

    return attach_proof(complaint_id, filename, proof.content_type, len(content))


@app.get("/api/complaints/{complaint_id}/proof")
async def download_complaint_proof(complaint_id: str):
    complaint = get_complaint(complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if not complaint.proof_filename:
        raise HTTPException(status_code=404, detail="No proof uploaded")

    stored_path = get_settings().database_file.parent / "proofs" / complaint_id.upper() / complaint.proof_filename
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Proof file not found")
    return FileResponse(stored_path, filename=complaint.proof_filename, media_type=complaint.proof_content_type)


@app.get("/api/complaints/{complaint_id}/pdf")
def download_complaint_pdf(complaint_id: str):
    complaint = get_complaint(complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    y = height - 70

    pdf.setTitle(f"NammaResolve Report - {complaint.complaint_id}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "NammaResolve Civic Issue Report")
    y -= 45
    pdf.setFont("Helvetica", 11)

    fields = [
        ("Reference", complaint.complaint_id),
        ("Category", complaint.category.value),
        ("Area", complaint.area),
        ("Landmark", complaint.landmark or "Not provided"),
        ("Status", complaint.status),
        ("Confirmation", complaint.confirmation_status),
        ("Created", complaint.created_at.isoformat()),
    ]
    for label, value in fields:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(50, y, f"{label}: ")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(115, y, str(value)[:95])
        y -= 24

    y -= 10
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Description")
    y -= 20
    pdf.setFont("Helvetica", 10)
    description = complaint.description
    for line in _wrap_pdf_text(description, 95):
        pdf.drawString(50, y, line)
        y -= 15

    if complaint.voice_session_id:
        y -= 12
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(50, y, "Voice session")
        pdf.setFont("Helvetica", 9)
        pdf.drawString(115, y, complaint.voice_session_id)

    y -= 35
    pdf.setFont("Helvetica", 8)
    pdf.drawString(50, y, "This is an internal NammaResolve prototype report, not an official government complaint.")
    pdf.save()

    output.seek(0)
    return StreamingResponse(output, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{complaint.complaint_id}.pdf"'
    })


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
@app.post("/api/voice/session", response_model=VoiceSessionOut)
def create_voice_session(payload: VoiceSessionRequest):
    """Start an Agora Conversational AI session using Murf Falcon TTS."""
    try:
        session = start_voice_session(payload.language)

    except RuntimeError as exc:
        logger.exception("Voice session configuration failed")
        raise HTTPException(
            status_code=503,
            detail=str(exc)
        ) from exc

    except Exception as exc:
        logger.exception("Agora voice session creation failed")
        raise HTTPException(
            status_code=502,
            detail=f"Could not start Agora voice session: {exc}"
        ) from exc

    settings = get_settings()

    return VoiceSessionOut(
        app_id=settings.agora_app_id,
        channel=session.channel,
        token=session.token,
        uid=session.uid,
        agent_session_id=session.agent_session_id,
        expires_at=session.expires_at,
    )

@app.post("/api/voice/session/{agent_session_id}/transcript", response_model=TranscriptEntryOut)
def add_voice_transcript(agent_session_id: str, payload: TranscriptEntry):
    return append_transcript_entry(
        agent_session_id,
        payload.speaker,
        payload.text,
        payload.is_final,
    )


@app.get("/api/voice/session/{agent_session_id}/transcript", response_model=list[TranscriptEntryOut])
def get_voice_transcript(agent_session_id: str):
    return list_transcript_entries(agent_session_id)


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
