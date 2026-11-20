# NammaResolve

**A voice-first civic issue reporting assistant for Bengaluru residents.** Residents can report common neighbourhood problems, receive an internal tracking reference, and check report status through a conversational voice agent.

> This is a hackathon prototype. A NammaResolve reference is an internal demo ID, not an official BBMP complaint or government acknowledgement. The current starter stores reports locally in SQLite and does not submit them to BBMP.

## What's included in this starter

- FastAPI backend written in Python.
- Simple responsive website served by FastAPI.
- Complaint creation and listing with SQLite persistence.
- Agora Conversational AI voice session setup using the Agora Python Agent SDK.
- Murf Falcon TTS configured as the Agora agent's speech provider.
- Agora custom tools for the agent to create a resident-confirmed complaint and retrieve its status.
- Server-generated RTC token for the browser microphone client.

## Tech stack

- Python 3.11+
- FastAPI + Pydantic
- SQLite (starter database; easy to replace with PostgreSQL/PostGIS later)
- Agora Conversational AI (`agora-agents` Python SDK)
- Murf Falcon TTS
- Agora Web SDK for browser audio transport (the website UI is plain HTML/CSS/JS; application backend is Python)

## 1. Create your virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate           # macOS / Linux
# .venv\\Scripts\\activate          # Windows PowerShell

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Configure API credentials

```bash
cp .env.example .env
```

Fill the values in `.env`:

| Variable | Where it comes from |
|---|---|
| `AGORA_APP_ID` | Agora Console project |
| `AGORA_APP_CERTIFICATE` | Agora Console project; keep it server-side |
| `MURF_API_KEY` | Murf API dashboard |
| `MURF_VOICE_ID` | A Falcon-compatible voice ID from Murf |
| `TOOL_API_KEY` | Generate a long random secret for securing the tool endpoints |
| `PUBLIC_BASE_URL` | Public HTTPS URL that reaches this FastAPI app |

The starter uses Agora-managed LLM/STT configuration in the Agent SDK example path. You can switch to BYOK providers later. The initial conversation language is English (`en-US`); Kannada and other Indian-language support should be added as a separate iteration after validating Agora/Murf voice and STT combinations.

## 3. Start the website

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Open <http://localhost:8000>. API docs are at <http://localhost:8000/docs>.

The complaint form works locally without Agora credentials. Reports are saved in `data/nammaresolve.db`.

## 4. Enable the Agora voice agent and its tools

Agora custom tools call your backend from Agora's infrastructure. This means the tool endpoint must be reachable over **HTTPS**; `localhost` is not reachable by Agora. During local development, expose port 8000 using a secure HTTPS tunnel (for example, ngrok or Cloudflare Tunnel), then set the resulting URL in `.env`:

```env
PUBLIC_BASE_URL=https://your-public-tunnel.example
TOOL_API_KEY=your-own-long-random-secret
```

Restart the FastAPI server after editing `.env`. Then click **Start a conversation**. The backend starts an Agora Conversational AI session configured with Murf Falcon TTS, creates a browser RTC token, and the web page joins the same Agora channel with the microphone.

The voice agent is instructed to collect and confirm the complaint category, description and area before calling the `createCivicComplaint` tool. It can also call `getComplaintStatus` when the resident provides an exact NammaResolve reference.

## 5. Test the complaint API without voice

Create a report:

```bash
curl -X POST http://localhost:8000/api/complaints \\
  -H 'Content-Type: application/json' \\
  -d '{"category":"garbage","description":"Garbage has not been collected for three days.","area":"Kalyan Nagar","landmark":"Near 5th Main Road"}'
```

List recent reports:

```bash
curl http://localhost:8000/api/complaints
```

Get one report (replace the sample ID with the generated value):

```bash
curl http://localhost:8000/api/complaints/NM-YYMMDD-XXXXX
```

## Project layout

```text
NammaResolve/
├── backend/
│   └── app/
│       ├── services/
│       │   └── agora.py       # Agora + Murf agent and tool definitions
│       ├── config.py          # Environment settings
│       ├── database.py        # SQLite persistence
│       ├── main.py            # FastAPI routes
│       └── schemas.py         # Request/response models
├── frontend/
│   ├── app.js                 # Browser interaction + Agora RTC client
│   ├── index.html
│   └── styles.css
├── tests/
├── .env.example
├── .gitignore
├── main.py
└── requirements.txt
```

## Current limitations / next iterations

1. Reports are stored only in a local SQLite database.
2. No official BBMP integration exists yet; the app must not claim to submit government complaints.
3. No photo upload, GPS capture, ward mapping, duplicate grouping, notifications or administrator login yet.
4. The voice starter is English-first. Validate language availability and pronunciation before enabling Kannada in the UI.
5. The Agora tool callbacks require a public HTTPS backend and a configured `TOOL_API_KEY`.

## Security notes

- Never commit `.env`, Agora App Certificate, Murf API key or `TOOL_API_KEY`.
- Keep Agora token generation on the backend. The browser receives only a short-lived RTC token.
- Rotate any API keys accidentally committed to source control.
- Use HTTPS and authentication before deploying this prototype for public use.
