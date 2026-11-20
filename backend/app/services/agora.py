import secrets
import time
from dataclasses import dataclass
from threading import RLock

from backend.app.config import get_settings

SYSTEM_PROMPT = """
You are NammaResolve, a helpful civic issue reporting assistant for Bengaluru residents.
Speak in a warm, concise, respectful way. The user may speak English; ask one clear question
at a time. Help residents report garbage collection, potholes, broken streetlights, drainage,
water leakage and other local civic problems.

To create a complaint, collect and confirm: category, a clear description, area/locality, and
an optional landmark. Do not create a complaint until the resident has explicitly confirmed
that the details are correct. Then call createCivicComplaint. Read the returned NammaResolve
reference ID and clearly explain that this is an internal NammaResolve tracking reference, not
an official BBMP ticket or government acknowledgement.

When a resident asks about an existing report, ask for its NammaResolve reference ID and call
getComplaintStatus. Never invent complaint IDs, official ticket numbers, government actions,
ward assignments, contact details, timelines or resolutions. If a tool fails, explain that the
report was not submitted and offer the website form as a fallback.
""".strip()


def _tool_definitions(base_url: str) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "createCivicComplaint",
                "description": (
                    "Create a resident-approved complaint in the NammaResolve demo database. "
                    "Only call after confirming category, description and area with the resident."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["garbage", "pothole", "streetlight", "drainage", "water_leakage", "other"],
                        },
                        "description": {"type": "string", "description": "What happened and how long it has been happening."},
                        "area": {"type": "string", "description": "Bengaluru locality or area."},
                        "landmark": {"type": "string", "description": "Nearby landmark, if available."},
                    },
                    "required": ["category", "description", "area"],
                    "additionalProperties": False,
                },
            },
            "execution": {"mode": "sync"},
            "server": {
                "method": "POST",
                "url": f"{base_url}/api/tools/complaints",
                "headers": {
                    "Authorization": "{{template_variables.tool_api_key}}",
                    "Content-Type": "application/json",
                },
                "body": {
                    "category": "{{args.category}}",
                    "description": "{{args.description}}",
                    "area": "{{args.area}}",
                    "landmark": "{{args.landmark}}",
                },
                "timeout_ms": 10000,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "getComplaintStatus",
                "description": "Look up a NammaResolve complaint using its exact reference ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "complaint_id": {"type": "string", "description": "NammaResolve reference, e.g. NM-260101-AB123."}
                    },
                    "required": ["complaint_id"],
                    "additionalProperties": False,
                },
            },
            "execution": {"mode": "sync"},
            "server": {
                "method": "GET",
                "url": f"{base_url}/api/tools/complaints/{{{{args.complaint_id}}}}",
                "headers": {"Authorization": "{{template_variables.tool_api_key}}"},
                "timeout_ms": 7000,
            },
        },
    ]


@dataclass
class StartedVoiceSession:
    agent_session_id: str
    channel: str
    uid: int
    token: str
    expires_at: int


_active_sessions: dict[str, object] = {}
_sessions_lock = RLock()


def start_voice_session() -> StartedVoiceSession:
    # Keep the civic form/API usable even before voice SDK dependencies are installed.
    from agora_agent import Agent, Agora, Area, DeepgramSTT, OpenAI
    from agora_agent.agentkit.vendors import MurfTTS
    from agora_token_builder import RtcTokenBuilder

    settings = get_settings()
    required = {
        "AGORA_APP_ID": settings.agora_app_id,
        "AGORA_APP_CERTIFICATE": settings.agora_certificate,
        "MURF_API_KEY": settings.murf_secret,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    base_url = settings.public_base_url.rstrip("/")
    if not base_url.startswith("https://"):
        raise RuntimeError(
            "PUBLIC_BASE_URL must be an HTTPS URL reachable by Agora. "
            "For local development, expose port 8000 with a secure tunnel."
        )
    if settings.tool_secret == "replace-with-a-long-random-secret":
        raise RuntimeError("Set TOOL_API_KEY to a unique random secret before starting voice sessions.")

    agora_area = Area.US if settings.agora_area.upper() == "US" else Area.US
    client = Agora(
        area=agora_area,
        app_id=settings.agora_app_id,
        app_certificate=settings.agora_certificate,
    )

    tool_definitions = _tool_definitions(base_url)
    agent = (
        Agent(client=client, turn_detection={"language": "en-US"})
        .with_stt(DeepgramSTT(model=settings.agora_stt_model, language="en"))
        .with_llm(
            OpenAI(
                model=settings.agora_llm_model,
                system_messages=[{"role": "system", "content": SYSTEM_PROMPT}],
                greeting_message="Hello! I'm NammaResolve. Tell me about the civic issue you're facing in Bengaluru.",
                failure_message="Sorry, I'm having trouble right now. Please try again or use the report form.",
                max_history=30,
                tools=tool_definitions,
                template_variables={"tool_api_key": f"Bearer {settings.tool_secret}"},
            )
        )
        .with_tts(
            MurfTTS(
                key=settings.murf_secret,
                voice_id=settings.murf_voice_id,
                base_url=settings.murf_base_url,
                locale=settings.murf_locale,
                rate=0,
                pitch=0,
                model="FALCON",
                sample_rate=24000,
            )
        )
        .with_tools(True)
    )

    channel = f"nammaresolve-{secrets.token_hex(8)}"
    uid = 100000 + secrets.randbelow(700000)
    agent_uid = "900001"
    session = agent.create_session(
        channel=channel,
        agent_uid=agent_uid,
        remote_uids=[str(uid)],
        name=f"nammaresolve-{channel}",
        idle_timeout=300,
    )
    agent_session_id = session.start()
    with _sessions_lock:
        _active_sessions[agent_session_id] = session

    expires_at = int(time.time()) + 3600
    user_token = RtcTokenBuilder.buildTokenWithUid(
        settings.agora_app_id,
        settings.agora_certificate,
        channel,
        uid,
        1,  # Publisher: the resident publishes microphone audio.
        expires_at,
    )
    return StartedVoiceSession(
        agent_session_id=agent_session_id,
        channel=channel,
        uid=uid,
        token=user_token,
        expires_at=expires_at,
    )


def stop_voice_session(agent_session_id: str) -> bool:
    """Stop a session created by this process. Returns False if it is unknown."""
    with _sessions_lock:
        session = _active_sessions.pop(agent_session_id, None)
    if session is None:
        return False
    session.stop()  # type: ignore[attr-defined]
    return True
